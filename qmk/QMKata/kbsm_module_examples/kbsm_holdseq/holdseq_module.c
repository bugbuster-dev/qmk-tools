/* kbsm_holdseq — SRAM-loadable hold sequence module.
 *
 * Hold a primary key, tap a variable-length sequence of secondary keys,
 * release primary — lookup (primary, sequence) in config table, fire
 * expansion via send_string. On no-match, replay all consumed keys.
 */

#include "module_api.h"
#include "Holdseq.h"
#include "Holdseq.c"
#include "holdseq_def.h"

typedef struct {
    Holdseq sm;
    kbsm_env_t *env;
    uint16_t held_primary;
    char sequence[HOLDSEQ_MAX_SEQ_LEN];
    uint8_t seq_len;
    bool primary_committed_to_host;
    bool firing;
} holdseq_state_t;

static holdseq_state_t g_state;
static kbsm_t g_machine;

static char keycode_to_ascii(uint16_t kc) {
    for (uint8_t i = 0; keycode_to_char[i].kc != 0; i++)
        if (keycode_to_char[i].kc == kc) return keycode_to_char[i].ch;
    return 0;
}

static uint16_t char_to_keycode(char ch) {
    for (uint8_t i = 0; keycode_to_char[i].kc != 0; i++)
        if (keycode_to_char[i].ch == ch) return keycode_to_char[i].kc;
    return 0;
}

static int8_t find_primary(char ch) {
    for (uint8_t i = 0; i < MODULE_HOLDSEQ_COUNT; i++)
        if (module_holds[i].primary == ch) return (int8_t)i;
    return -1;
}

static int8_t find_sequence(char primary, uint8_t len) {
    for (uint8_t i = 0; i < MODULE_HOLDSEQ_COUNT; i++) {
        const char *seq = module_holds[i].sequence;
        if (module_holds[i].primary != primary) continue;
        uint8_t slen = 0;
        while (slen < HOLDSEQ_MAX_SEQ_LEN && seq[slen] != 0) slen++;
        if (slen != len) continue;
        bool match = true;
        for (uint8_t j = 0; j < len; j++)
            if (seq[j] != g_state.sequence[j]) { match = false; break; }
        if (match) return (int8_t)i;
    }
    return -1;
}

static void do_replay(void) {
    g_state.firing = true;
    g_state.env->tap_code16(g_state.held_primary);
    for (uint8_t i = 0; i < g_state.seq_len; i++) {
        uint16_t kc = char_to_keycode(g_state.sequence[i]);
        if (kc) g_state.env->tap_code16(kc);
    }
    g_state.firing = false;
}

static void reset_state(void) {
    g_state.seq_len = 0;
    g_state.primary_committed_to_host = false;
    g_state.firing = false;
}

static kbsm_result_t holdseq_handle(void *self, keyevent_t *event, keyrecord_t *record) {
    holdseq_state_t *st = (holdseq_state_t *)self;
    kbsm_env_t *env = st->env;
    uint16_t kc = env->get_record_keycode(record, true);

    if (st->firing) return KBSM_PASS;

    /* IDLE */
    if (st->sm.state_id == Holdseq_StateId_IDLE) {
        if (!event->pressed) return KBSM_PASS;
        char ch = keycode_to_ascii(kc);
        if (ch && find_primary(ch) >= 0) {
            st->held_primary = kc;
            reset_state();
            Holdseq_dispatch_event(&st->sm, Holdseq_EventId_ON_PRIMARY_PRESS);
            return KBSM_CONSUME;
        }
        return KBSM_PASS;
    }

    /* PRIMARY_HELD */
    if (st->sm.state_id == Holdseq_StateId_PRIMARY_HELD) {
        /* Release of primary without any secondary → normal tap */
        if (!event->pressed && kc == st->held_primary) {
            env->tap_code16(st->held_primary);
            Holdseq_dispatch_event(&st->sm, Holdseq_EventId_ON_PRIMARY_RELEASE);
            reset_state();
            return KBSM_CONSUME;
        }
        if (!event->pressed) return KBSM_PASS;

        char ch = keycode_to_ascii(kc);
        /* Non-printable → commit primary as hold */
        if (ch == 0 || ch == '\b' || ch == '\t' || ch == '\n' || ch == '\x7f') {
            env->register_code16(st->held_primary);
            st->primary_committed_to_host = true;
            Holdseq_dispatch_event(&st->sm, Holdseq_EventId_ON_OTHER_KEY);
            return KBSM_PASS;
        }
        /* Printable → start sequence */
        st->sequence[0] = ch;
        st->seq_len = 1;
        Holdseq_dispatch_event(&st->sm, Holdseq_EventId_ON_FIRST_SECONDARY);
        return KBSM_CONSUME;
    }

    /* COLLECTING */
    if (st->sm.state_id == Holdseq_StateId_COLLECTING) {
        /* Primary release → lookup + fire/replay */
        if (!event->pressed && kc == st->held_primary) {
            char primary_ch = keycode_to_ascii(st->held_primary);
            int8_t match = find_sequence(primary_ch, st->seq_len);
            st->firing = true;
            if (match >= 0) {
                env->send_string(module_holds[match].expansion);
            } else {
                env->tap_code16(st->held_primary);
                for (uint8_t i = 0; i < st->seq_len; i++) {
                    uint16_t k = char_to_keycode(st->sequence[i]);
                    if (k) env->tap_code16(k);
                }
            }
            st->firing = false;
            Holdseq_dispatch_event(&st->sm, Holdseq_EventId_ON_PRIMARY_RELEASE);
            reset_state();
            return KBSM_CONSUME;
        }
        if (!event->pressed) return KBSM_PASS;

        char ch = keycode_to_ascii(kc);
        /* Non-printable → break + replay */
        if (ch == 0 || ch == '\b' || ch == '\t' || ch == '\n' || ch == '\x7f') {
            do_replay();
            Holdseq_dispatch_event(&st->sm, Holdseq_EventId_ON_OTHER_KEY);
            reset_state();
            return KBSM_PASS;
        }
        /* Buffer full → break + replay */
        if (st->seq_len >= HOLDSEQ_MAX_SEQ_LEN) {
            do_replay();
            Holdseq_dispatch_event(&st->sm, Holdseq_EventId_ON_OTHER_KEY);
            reset_state();
            return KBSM_PASS;
        }
        /* Printable → accumulate */
        st->sequence[st->seq_len] = ch;
        st->seq_len++;
        Holdseq_dispatch_event(&st->sm, Holdseq_EventId_ON_SECONDARY_PRESS);
        return KBSM_CONSUME;
    }

    return KBSM_PASS;
}

static void holdseq_reset(void *self) {
    holdseq_state_t *st = (holdseq_state_t *)self;
    Holdseq_ctor(&st->sm);
    Holdseq_start(&st->sm);
    reset_state();
}

static kbsm_t *machine_get(void) { return &g_machine; }

static uint32_t module_init(kbsm_env_t *env) {
    if (!env) return 0xDEADBEEFu;
    g_state.env = env;
    reset_state();
    Holdseq_ctor(&g_state.sm);
    Holdseq_start(&g_state.sm);
    g_machine.instance = &g_state;
    g_machine.handle   = holdseq_handle;
    g_machine.tick     = NULL;
    g_machine.reset    = holdseq_reset;
    g_machine.name     = "holdseq_sram";
    g_machine.phase    = KBSM_PHASE_PRE_TAP;
    g_machine.priority = 65;
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
