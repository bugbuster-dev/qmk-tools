/* pipeline_sticky_combo — SRAM-loadable pipeline module.
 *
 * Mirrors the firmware-built sticky_combo feature in
 * quantum/features/sticky_combo_adapter.c, but routes all firmware
 * calls through the kbsm_env_t callback table received in init().
 * Sticky combo definitions live in combos_def.h (this directory) and
 * are baked into the module at build time.
 *
 * Slot 8 (default SRAM slot) on Keychron Q3 Max with MODULE_SRAM_ENABLE.
 * Header v3 — module_init_fn takes kbsm_env_t*.
 */

#include "module_api.h"
#include "StickyCombo.h"
#include "combos_def.h"

#ifndef QK_LEADER
#define QK_LEADER 0x7C73  /* QMK quantum keycode — unused here but kept for parity */
#endif

/* QK_TAP_DANCE range — also unused in sticky combo, here for parity with firmware adapter */

typedef struct {
    StickyCombo sm;
    kbsm_env_t *env;
    int8_t  active_combo;       /* index into module_sticky_combos[], -1 = none */
    bool    key1_held;
    bool    key2_held;
    /* Simultaneous-press detection */
    int8_t   pending_combo;
    bool     pending_is_key1;
    uint16_t pending_time;
    uint16_t pending_keycode;
    bool     pending_pressed_on_host;
} sticky_state_t;

#ifndef STICKY_COMBO_WINDOW_MS
#define STICKY_COMBO_WINDOW_MS 50
#endif

static sticky_state_t g_state = {.active_combo = -1, .pending_combo = -1};
static kbsm_t g_machine;

static int8_t find_combo_for_key(uint16_t kc, bool *is_key1, bool *is_key2) {
    for (uint8_t i = 0; i < MODULE_STICKY_COMBO_COUNT; i++) {
        if (module_sticky_combos[i].key1 == kc) {
            *is_key1 = true; *is_key2 = false;
            return (int8_t)i;
        }
        if (module_sticky_combos[i].key2 == kc) {
            *is_key1 = false; *is_key2 = true;
            return (int8_t)i;
        }
    }
    return -1;
}

static kbsm_result_t sticky_handle(void *self, keyevent_t *event, keyrecord_t *record) {
    sticky_state_t *st = (sticky_state_t *)self;
    kbsm_env_t *env = st->env;
    uint16_t kc = env->get_record_keycode(record, true);

     /* IDLE */
    if (st->sm.state_id == StickyCombo_StateId_IDLE) {
        if (!event->pressed) {
            if (st->pending_combo >= 0 && kc == st->pending_keycode) {
                if (st->pending_pressed_on_host) {
                    env->unregister_code16(kc);
                } else {
                    env->tap_code16(kc);
                }
                st->pending_combo = -1;
                st->pending_pressed_on_host = false;
                return KBSM_CONSUME;
            }
            return KBSM_PASS;
        }

        bool is_key1 = false, is_key2 = false;
        int8_t combo = find_combo_for_key(kc, &is_key1, &is_key2);

        if (combo < 0) {
            if (st->pending_combo >= 0 && !st->pending_pressed_on_host) {
                env->register_code16(st->pending_keycode);
                st->pending_pressed_on_host = true;
            }
            st->pending_combo = -1;
            return KBSM_PASS;
        }

        if (st->pending_combo == combo &&
            (env->timer_elapsed(st->pending_time) <= STICKY_COMBO_WINDOW_MS) &&
            ((st->pending_is_key1 && is_key2) || (!st->pending_is_key1 && is_key1))) {
            st->active_combo = combo;
            st->key1_held = true;
            st->key2_held = true;
            st->pending_combo = -1;
            st->pending_pressed_on_host = false;

            uint16_t action = module_sticky_combos[combo].combo_action;
            if (action != KC_NO) env->tap_code16(action);

            StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_COMBO_PRESS);
            return KBSM_CONSUME;
        }

        if (st->pending_combo >= 0) {
            if (!st->pending_pressed_on_host) {
                env->register_code16(st->pending_keycode);
                st->pending_pressed_on_host = true;
            }
            st->pending_combo = -1;
            st->pending_pressed_on_host = false;
        }

        st->pending_combo = combo;
        st->pending_keycode = kc;
        st->pending_is_key1 = is_key1;
        st->pending_time = env->timer_read();
        st->pending_pressed_on_host = false;
        return KBSM_CONSUME;
    }

    /* ARMED_BOTH */
    if (st->sm.state_id == StickyCombo_StateId_ARMED_BOTH) {
        if (st->active_combo < 0) return KBSM_PASS;
        uint16_t key1 = module_sticky_combos[st->active_combo].key1;
        uint16_t key2 = module_sticky_combos[st->active_combo].key2;
        if (kc != key1 && kc != key2) return KBSM_PASS;
        if (event->pressed) return KBSM_CONSUME;

        if (kc == key1) {
            st->key1_held = false;
            if (st->key2_held) {
                StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_RELEASE_KEY1);
            } else {
                StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_RELEASE_BOTH);
                st->active_combo = -1;
            }
        } else {
            st->key2_held = false;
            if (st->key1_held) {
                StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_RELEASE_KEY2);
            } else {
                StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_RELEASE_BOTH);
                st->active_combo = -1;
            }
        }
        return KBSM_CONSUME;
    }

    /* ARMED_FOR_KEY1: key2 still held; tapping key1 fires tap_action_1 */
    if (st->sm.state_id == StickyCombo_StateId_ARMED_FOR_KEY1) {
        if (st->active_combo < 0) return KBSM_PASS;
        uint16_t key1 = module_sticky_combos[st->active_combo].key1;
        uint16_t key2 = module_sticky_combos[st->active_combo].key2;
        if (kc == key1) {
            if (event->pressed) {
                uint16_t action = module_sticky_combos[st->active_combo].tap_action_1;
                if (action != KC_NO) env->tap_code16(action);
                StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_TAP_KEY1);
            }
            return KBSM_CONSUME;
        }
        if (kc == key2 && !event->pressed) {
            st->key2_held = false;
            StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_RELEASE_KEY2);
            st->active_combo = -1;
            return KBSM_CONSUME;
        }
        return KBSM_PASS;
    }

    /* ARMED_FOR_KEY2: key1 still held; tapping key2 fires tap_action_2 */
    if (st->sm.state_id == StickyCombo_StateId_ARMED_FOR_KEY2) {
        if (st->active_combo < 0) return KBSM_PASS;
        uint16_t key1 = module_sticky_combos[st->active_combo].key1;
        uint16_t key2 = module_sticky_combos[st->active_combo].key2;
        if (kc == key2) {
            if (event->pressed) {
                uint16_t action = module_sticky_combos[st->active_combo].tap_action_2;
                if (action != KC_NO) env->tap_code16(action);
                StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_TAP_KEY2);
            }
            return KBSM_CONSUME;
        }
        if (kc == key1 && !event->pressed) {
            st->key1_held = false;
            StickyCombo_dispatch_event(&st->sm, StickyCombo_EventId_ON_RELEASE_KEY1);
            st->active_combo = -1;
            return KBSM_CONSUME;
        }
        return KBSM_PASS;
    }

    return KBSM_PASS;
}

static void sticky_tick(void *self) {
    sticky_state_t *st = (sticky_state_t *)self;
    if (st->pending_combo < 0) return;
    if (st->env->timer_elapsed(st->pending_time) <= STICKY_COMBO_WINDOW_MS) return;
    if (!st->pending_pressed_on_host) {
        st->env->register_code16(st->pending_keycode);
        st->pending_pressed_on_host = true;
    }
}

static void sticky_reset(void *self) {
    sticky_state_t *st = (sticky_state_t *)self;
    StickyCombo_ctor(&st->sm);
    StickyCombo_start(&st->sm);
    st->active_combo = -1;
    st->pending_combo = -1;
    st->key1_held = false;
    st->key2_held = false;
    st->pending_pressed_on_host = false;
}

static kbsm_t *machine_get(void) {
    return &g_machine;
}

 /* ---- lifecycle ---- */

static uint32_t module_init(kbsm_env_t *env) {
    if (!env) return 0xDEADBEEFu;  /* firmware built without pipeline support */

    /* With -fPIC, GCC emits "LDR + ADD pc" for every symbol reference, so
       &g_machine, sticky_handle, etc. evaluate to the actual runtime SRAM
       address at any load offset. No manual rebasing via env->module_base
       is needed (or correct — adding base would double-count and land in
       the peripheral region around 0x40xxxxxx). */
    g_state.env = env;
    StickyCombo_ctor(&g_state.sm);
    StickyCombo_start(&g_state.sm);
    g_state.active_combo = -1;
    g_state.pending_combo = -1;
    g_state.key1_held = false;
    g_state.key2_held = false;
    g_state.pending_pressed_on_host = false;

    g_machine.instance = &g_state;
    g_machine.handle   = sticky_handle;
    g_machine.tick     = sticky_tick;
    g_machine.reset    = sticky_reset;
    g_machine.name     = "sticky_combo_sram";
    g_machine.phase    = KBSM_PHASE_PRE_TAP;
    g_machine.priority = 40;

    env->kbsm_register(&g_machine);
    return MODULE_INIT_MAGIC;
}

static uint32_t module_deinit(void) {
    if (g_state.env) {
        g_state.env->kbsm_unregister(&g_machine);
    }
    return 0;
}

/* Hook table. Pipeline modules export an kbsm_t* via GET_MACHINE
   for firmware introspection; the actual registration happens in init. */
MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_HOOK_INIT]                       = module_init,
    [MODULE_HOOK_DEINIT]                     = module_deinit,
    [MODULE_KBSM_HOOK_GET_MACHINE]       = machine_get,
};
