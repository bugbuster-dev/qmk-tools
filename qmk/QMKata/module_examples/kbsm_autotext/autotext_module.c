/* kbsm_autotext — SRAM-loadable autotext module.
 *
 * Abbreviation expansion at the firmware level. Watch typed sequences,
 * match against a configurable trigger table, replace matches with
 * longer expansions via send_string.
 *
 * No firmware-side counterpart exists. The trigger table lives in
 * autotext_def.h (this directory) and is baked into the module at build
 * time. All firmware calls go through the kbsm_env_t callback table
 * received in init().
 *
 * See docs/plans/2026-05-24-autotext-design.md in the firmware repo for
 * design rationale and edge-case analysis.
 *
 * Slot 8 (default SRAM slot) on Keychron Q3 Max with MODULE_SRAM_ENABLE.
 * Header v5 — module_init_fn takes kbsm_env_t* (v5 ABI with send_string).
 */

#include "module_api.h"
#include "Autotext.h"
#include "Autotext.c"
#include "autotext_def.h"

typedef struct {
    Autotext sm;
    kbsm_env_t *env;
    char buffer[AUTOTEXT_MAX_TRIGGER_LEN];
    uint8_t buffer_len;
} autotext_state_t;

static autotext_state_t g_state;
static kbsm_t g_machine;

/* Look up a keycode in the keycode_to_char table.
 * Returns the printable character, or 0 if not found.
 * Shift-modified characters are not handled in v1 (no get_mods() in kbsm_env_t). */
static char keycode_to_ascii(uint16_t kc) {
    const keycode_char_t *table = keycode_to_char;
    for (uint8_t i = 0; table[i].kc != 0; i++) {
        if (table[i].kc == kc) return table[i].ch;
    }
    return 0;
}

/* Shift-modified characters are not handled in v1 (no get_mods() in kbsm_env_t). */

/* Find the best matching trigger for the current buffer.
 * Returns:
 *   >= 0: exact match index
 *   -1: no match, but buffer is a prefix of some trigger
 *   -2: no match, buffer is not a prefix of any trigger */
static int8_t find_trigger(void) {
    if (g_state.buffer_len == 0) return -2;

    bool has_prefix = false;
    int8_t exact_match = -2;

    for (uint8_t i = 0; i < MODULE_AUTOTEXT_COUNT; i++) {
        const char *trigger = module_autotext[i].trigger;
        uint8_t trigger_len = 0;
        while (trigger[trigger_len] != 0 && trigger_len < AUTOTEXT_MAX_TRIGGER_LEN) {
            trigger_len++;
        }

        /* Check for exact match */
        if (trigger_len == g_state.buffer_len) {
            bool match = true;
            for (uint8_t j = 0; j < g_state.buffer_len; j++) {
                if (trigger[j] != g_state.buffer[j]) {
                    match = false;
                    break;
                }
            }
            if (match) {
                exact_match = (int8_t)i;
                break; /* exact match wins */
            }
        }

        /* Check for prefix match */
        if (trigger_len > g_state.buffer_len) {
            bool prefix = true;
            for (uint8_t j = 0; j < g_state.buffer_len; j++) {
                if (trigger[j] != g_state.buffer[j]) {
                    prefix = false;
                    break;
                }
            }
            if (prefix) {
                has_prefix = true;
            }
        }
    }

    /* Debug: dump first trigger's first char if no match found */
    if (exact_match < 0 && !has_prefix && g_state.buffer_len == 1) {
        mprintf("[autotext] diag: buf[0]='%c' (%02x), trigger[0][0]='%c' (%02x), ptr=%p\n",
                g_state.buffer[0], (uint8_t)g_state.buffer[0],
                module_autotext[0].trigger[0], (uint8_t)module_autotext[0].trigger[0],
                (void *)module_autotext[0].trigger);
    }

    if (exact_match >= 0) return exact_match;
    if (has_prefix) return -1;
    return -2;
}

/* Send backspaces to delete the typed trigger, then send the expansion. */
static void fire_trigger(const char *expansion) {
    mprintf("[autotext] fire: %d backspaces, expansion='%s'\n",
            g_state.buffer_len, expansion);
    /* Send backspaces to delete the trigger */
    for (uint8_t i = 0; i < g_state.buffer_len; i++) {
        g_state.env->tap_code16(KC_BSPC);
    }
    /* Send the expansion */
    g_state.env->send_string(expansion);
}

/* Clear the buffer and reset to IDLE. */
static void reset_buffer(void) {
    g_state.buffer_len = 0;
    /* No need to zero the buffer — buffer_len is the authoritative length */
}

static kbsm_result_t autotext_handle(void *self, keyevent_t *event, keyrecord_t *record) {
    autotext_state_t *st = (autotext_state_t *)self;
    kbsm_env_t *env = st->env;
    uint16_t kc = env->get_record_keycode(record, true);

    /* Only care about key presses */
    if (!event->pressed) {
        return KBSM_PASS;
    }

    /* Convert keycode to ASCII character */
    char ch = keycode_to_ascii(kc);
    mprintf("[autotext] press kc=0x%04X ch='%c' buf_len=%d state=%s\n",
            kc, ch, st->buffer_len,
            st->sm.state_id == Autotext_StateId_IDLE ? "IDLE" : "ACCUM");

    /* Handle backspace: truncate buffer by one */
    if (ch == '\b') {
        if (st->buffer_len > 0) {
            st->buffer_len--;
            mprintf("[autotext] backspace -> buf_len=%d\n", st->buffer_len);
        }
        return KBSM_PASS;
    }

    /* Handle non-printable characters: break any partial match */
    if (ch == 0 || ch == '\t' || ch == '\n' || ch == '\x7f') {
        /* Non-printable character — break any partial match */
        if (st->buffer_len > 0) {
            mprintf("[autotext] non-printable, break match\n");
            Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_BREAK_MATCH);
            reset_buffer();
        }
        return KBSM_PASS;
    }

    /* Append character to buffer */
    if (st->buffer_len >= AUTOTEXT_MAX_TRIGGER_LEN) {
        /* Buffer overflow — force reset */
        mprintf("[autotext] buffer overflow, reset\n");
        Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_BREAK_MATCH);
        reset_buffer();
        return KBSM_PASS;
    }

    st->buffer[st->buffer_len] = ch;
    st->buffer_len++;

    /* Find matching trigger */
    int8_t result = find_trigger();

    if (result >= 0) {
        /* Exact match — fire the trigger */
        mprintf("[autotext] EXACT MATCH '%s' -> '%s'\n",
                st->buffer, module_autotext[result].expansion);
        fire_trigger(module_autotext[result].expansion);
        Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_FULL_MATCH);
        reset_buffer();
    } else if (result == -1) {
        /* Prefix match — still accumulating */
        mprintf("[autotext] prefix match '%.*s'\n", st->buffer_len, st->buffer);
        if (st->buffer_len == 1) {
            Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_FIRST_MATCH_CHAR);
        } else {
            Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_EXTEND_MATCH);
        }
  } else {
        /* No match — break and check if this char starts any trigger */
        mprintf("[autotext] no match '%.*s' (find_trigger=%d), break\n", st->buffer_len, st->buffer, result);
        Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_BREAK_MATCH);

        /* Check if this character alone starts any trigger */
        bool starts_match = false;
        for (uint8_t i = 0; i < MODULE_AUTOTEXT_COUNT; i++) {
            if (module_autotext[i].trigger[0] == ch) {
                starts_match = true;
                break;
            }
        }

        if (starts_match) {
            /* This character starts a new match — keep it in buffer */
            st->buffer[0] = ch;
            st->buffer_len = 1;
            mprintf("[autotext] new match start '%c'\n", ch);
            Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_FIRST_MATCH_CHAR);
        } else {
            /* No match — clear buffer */
            reset_buffer();
        }
    }

    return KBSM_PASS;
}

static void autotext_reset(void *self) {
    autotext_state_t *st = (autotext_state_t *)self;
    Autotext_ctor(&st->sm);
    Autotext_start(&st->sm);
    reset_buffer();
}

static kbsm_t *machine_get(void) {
    return &g_machine;
}

/* ---- lifecycle ---- */

static uint32_t module_init(kbsm_env_t *env) {
    if (!env) return 0xDEADBEEFu;  /* firmware built without kbsm support */

    mprintf("[autotext] init: env=0x%lx, send_string=0x%lx\n",
            (unsigned long)env, (unsigned long)env->send_string);

    g_state.env = env;
    Autotext_ctor(&g_state.sm);
    Autotext_start(&g_state.sm);
    reset_buffer();

    g_machine.instance = &g_state;
    g_machine.handle   = autotext_handle;
    g_machine.tick     = NULL;  /* no periodic logic; pure event-driven */
    g_machine.reset    = autotext_reset;
    g_machine.name     = "autotext_sram";
    g_machine.phase    = KBSM_PHASE_PRE_TAP;
    g_machine.priority = 70;  /* below dyad (60), sticky_combo (40), vim_modal (50) */

    env->kbsm_register(&g_machine);
    mprintf("[autotext] registered %d triggers\n", MODULE_AUTOTEXT_COUNT);
    /* Diagnostic: dump trigger table to verify string pointers resolve */
    for (uint8_t i = 0; i < MODULE_AUTOTEXT_COUNT; i++) {
        mprintf("[autotext] trigger[%d]: '%s' -> '%s'\n",
                i, module_autotext[i].trigger, module_autotext[i].expansion);
    }
    return MODULE_INIT_MAGIC;
}

static uint32_t module_deinit(void) {
    if (g_state.env) {
        g_state.env->kbsm_unregister(&g_machine);
    }
    return 0;
}

MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_HOOK_INIT]              = module_init,
    [MODULE_HOOK_DEINIT]            = module_deinit,
    [MODULE_KBSM_HOOK_GET_MACHINE]  = machine_get,
};
