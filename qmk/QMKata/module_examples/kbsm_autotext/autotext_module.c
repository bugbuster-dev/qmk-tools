/* kbsm_autotext — SRAM-loadable autotext module.
 *
 * Abbreviation expansion at the firmware level. Watch typed sequences,
 * match against a configurable trigger table, replace matches with
 * longer expansions via send_string.
 *
 * All firmware calls go through the kbsm_env_t callback table received
 * in init(). Trigger table and keycode→ASCII lookup live in autotext_def.h.
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
    bool firing; /* guard: true while tap_code16/send_string in progress */
} autotext_state_t;

static autotext_state_t g_state;
static kbsm_t g_machine;

static char keycode_to_ascii(uint16_t kc) {
    const keycode_char_t *table = keycode_to_char;
    for (uint8_t i = 0; table[i].kc != 0; i++) {
        if (table[i].kc == kc) return table[i].ch;
    }
    return 0;
}

static int8_t find_trigger(void) {
    if (g_state.buffer_len == 0) return -2;

    bool has_prefix = false;
    int8_t exact_match = -2;

    for (uint8_t i = 0; i < MODULE_AUTOTEXT_COUNT; i++) {
        const char *trigger = module_autotext[i].trigger;
        uint8_t trigger_len = 0;
        while (trigger_len < AUTOTEXT_MAX_TRIGGER_LEN && trigger[trigger_len] != 0) {
            trigger_len++;
        }

        if (trigger_len == g_state.buffer_len) {
            bool match = true;
            for (uint8_t j = 0; j < g_state.buffer_len; j++) {
                if (trigger[j] != g_state.buffer[j]) { match = false; break; }
            }
            if (match) {
                exact_match = (int8_t)i;
                break;
            }
        }

        if (trigger_len > g_state.buffer_len) {
            bool prefix = true;
            for (uint8_t j = 0; j < g_state.buffer_len; j++) {
                if (trigger[j] != g_state.buffer[j]) { prefix = false; break; }
            }
            if (prefix) has_prefix = true;
        }
    }

    if (exact_match >= 0) return exact_match;
    if (has_prefix) return -1;
    return -2;
}

static void fire_trigger(const char *expansion) {
    mprintf("[at] FIRE bs=%d exp='%s'\n", g_state.buffer_len, expansion);
    g_state.firing = true;
    for (uint8_t i = 0; i < g_state.buffer_len; i++) {
        g_state.env->tap_code16(KC_BSPC);
    }
    g_state.env->send_string(expansion);
    g_state.firing = false;
    mprintf("[at] DONE\n");
}

static void reset_buffer(void) {
    g_state.buffer_len = 0;
}

static kbsm_result_t autotext_handle(void *self, keyevent_t *event, keyrecord_t *record) {
    autotext_state_t *st = (autotext_state_t *)self;
    kbsm_env_t *env = st->env;
    uint16_t kc = env->get_record_keycode(record, true);

    if (!event->pressed) {
        if (st->firing) mprintf("[at] release while firing, pass\n");
        return KBSM_PASS;
    }

    if (st->firing) {
        mprintf("[at] firing guard: pass kc=0x%04X\n", kc);
        return KBSM_PASS;
    }

    char ch = keycode_to_ascii(kc);
    mprintf("[at] press kc=0x%04X ch='%c'(%02x) buf=%d\n", kc, ch, (uint8_t)ch, st->buffer_len);

    if (ch == '\b') {
        if (st->buffer_len > 0) st->buffer_len--;
        return KBSM_PASS;
    }

    if (ch == 0 || ch == '\t' || ch == '\n' || ch == '\x7f') {
        if (st->buffer_len > 0) {
            Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_BREAK_MATCH);
            reset_buffer();
        }
        return KBSM_PASS;
    }

    if (st->buffer_len >= AUTOTEXT_MAX_TRIGGER_LEN) {
        Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_BREAK_MATCH);
        reset_buffer();
        return KBSM_PASS;
    }

    st->buffer[st->buffer_len] = ch;
    st->buffer_len++;

    int8_t result = find_trigger();

    if (result >= 0) {
        mprintf("[at] MATCH idx=%d '%s'->'%s' consume, backspaces=%d\n",
                result, module_autotext[result].trigger,
                module_autotext[result].expansion, st->buffer_len - 1);
        st->buffer_len--;
        fire_trigger(module_autotext[result].expansion);
        Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_FULL_MATCH);
        reset_buffer();
        return KBSM_CONSUME;
    } else if (result == -1) {
        mprintf("[at] prefix '%.*s' len=%d\n", st->buffer_len, st->buffer, st->buffer_len);
        if (st->buffer_len == 1) {
            Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_FIRST_MATCH_CHAR);
        } else {
            Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_EXTEND_MATCH);
        }
    } else {
        Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_BREAK_MATCH);

        bool starts_match = false;
        for (uint8_t i = 0; i < MODULE_AUTOTEXT_COUNT; i++) {
            if (module_autotext[i].trigger[0] == ch) { starts_match = true; break; }
        }

        mprintf("[at] nomatch starts=%d buf='%.*s'\n", starts_match, st->buffer_len, st->buffer);

        if (starts_match) {
            st->buffer[0] = ch;
            st->buffer_len = 1;
            Autotext_dispatch_event(&st->sm, Autotext_EventId_ON_FIRST_MATCH_CHAR);
        } else {
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

static kbsm_t *machine_get(void) { return &g_machine; }

static uint32_t module_init(kbsm_env_t *env) {
    if (!env) return 0xDEADBEEFu;

    g_state.env = env;
    Autotext_ctor(&g_state.sm);
    Autotext_start(&g_state.sm);
    reset_buffer();

    g_machine.instance = &g_state;
    g_machine.handle   = autotext_handle;
    g_machine.tick     = NULL;
    g_machine.reset    = autotext_reset;
    g_machine.name     = "autotext_sram";
    g_machine.phase    = KBSM_PHASE_PRE_TAP;
    g_machine.priority = 70;

    env->kbsm_register(&g_machine);
    return MODULE_INIT_MAGIC;
}

static uint32_t module_deinit(void) {
    if (g_state.env) g_state.env->kbsm_unregister(&g_machine);
    return 0;
}

MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_HOOK_INIT]              = module_init,
    [MODULE_HOOK_DEINIT]            = module_deinit,
    [MODULE_KBSM_HOOK_GET_MACHINE]  = machine_get,
};
