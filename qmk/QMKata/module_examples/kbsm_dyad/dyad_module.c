/* kbsm_dyad — SRAM-loadable behavior module.
 *
 * Dyad: hold primary key, tap secondary key, fire arbitrary output.
 * 2D lookup table (primary, secondary) → output.
 *
 * No firmware-side counterpart exists. The dyad table lives in
 * dyad_def.h (this directory) and is baked into the module at build
 * time. All firmware calls go through the kbsm_env_t callback table
 * received in init().
 *
 * See docs/plans/2026-05-24-dyad-design.md in the firmware repo for
 * design rationale and edge-case analysis.
 *
 * Slot 8 (default SRAM slot) on Keychron Q3 Max with MODULE_SRAM_ENABLE.
 * Header v4 — module_init_fn takes kbsm_env_t*.
 */

#include "module_api.h"
#include "Dyad.h"
#include "Dyad.c"
#include "dyad_def.h"

typedef struct {
    Dyad sm;
    kbsm_env_t *env;
    uint16_t held_primary;         /* meaningful when state != IDLE */
    int8_t   active_dyad_index;    /* -1 if no dyad armed; else index into module_dyads[] */
    bool     primary_committed_to_host;
} dyad_state_t;

static dyad_state_t g_state = {.active_dyad_index = -1};
static kbsm_t g_machine;

/* Look up (primary, secondary) in the dyad table.
 * Returns the matching row index, or -1 if not found.
 * First match wins; later rows with the same pair are ignored. */
static int8_t find_dyad(uint16_t primary, uint16_t secondary) {
    for (uint8_t i = 0; i < MODULE_DYAD_COUNT; i++) {
        if (module_dyads[i].primary == primary &&
            module_dyads[i].secondary == secondary) {
            return (int8_t)i;
        }
    }
    return -1;
}

/* True if `kc` appears as the primary in at least one dyad. */
static bool is_dyad_primary(uint16_t kc) {
    for (uint8_t i = 0; i < MODULE_DYAD_COUNT; i++) {
        if (module_dyads[i].primary == kc) return true;
    }
    return false;
}

static kbsm_result_t dyad_handle(void *self, keyevent_t *event, keyrecord_t *record) {
    dyad_state_t *st = (dyad_state_t *)self;
    kbsm_env_t *env = st->env;
    uint16_t kc = env->get_record_keycode(record, true);

    /* IDLE */
    if (st->sm.state_id == Dyad_StateId_IDLE) {
        if (event->pressed && is_dyad_primary(kc)) {
            st->held_primary = kc;
            st->active_dyad_index = -1;
            st->primary_committed_to_host = false;
            Dyad_dispatch_event(&st->sm, Dyad_EventId_ON_PRIMARY_PRESS);
            return KBSM_CONSUME;
        }
        return KBSM_PASS;
    }

    /* PRIMARY_HELD: primary is held, decision deferred */
    if (st->sm.state_id == Dyad_StateId_PRIMARY_HELD) {
        if (event->pressed) {
            /* Press of a candidate secondary? */
            int8_t i = find_dyad(st->held_primary, kc);
            if (i >= 0) {
                env->tap_code16(module_dyads[i].output);
                st->active_dyad_index = i;
                Dyad_dispatch_event(&st->sm, Dyad_EventId_ON_SECONDARY_MATCH);
                return KBSM_CONSUME;
            }
            /* Some other key — primary becomes a normal hold */
            env->register_code16(st->held_primary);
            st->primary_committed_to_host = true;
            Dyad_dispatch_event(&st->sm, Dyad_EventId_ON_OTHER_KEY);
            return KBSM_PASS;
        }

        /* Release */
        if (kc == st->held_primary) {
            /* Released without secondary match → emit as a normal tap */
            env->tap_code16(st->held_primary);
            Dyad_dispatch_event(&st->sm, Dyad_EventId_ON_PRIMARY_RELEASE);
            return KBSM_CONSUME;
        }
        return KBSM_PASS;
    }

    /* ARMED: primary still held, secondary has fired at least once */
    if (st->sm.state_id == Dyad_StateId_ARMED) {
        if (event->pressed) {
            /* Repeat or new secondary for same primary */
            int8_t i = find_dyad(st->held_primary, kc);
            if (i >= 0) {
                env->tap_code16(module_dyads[i].output);
                st->active_dyad_index = i;
                Dyad_dispatch_event(&st->sm, Dyad_EventId_ON_SECONDARY_REPEAT);
                return KBSM_CONSUME;
            }
            /* Some unrelated third key — pass through */
            return KBSM_PASS;
        }

        /* Release of primary ends the dyad */
        if (kc == st->held_primary) {
            if (st->primary_committed_to_host) {
                /* Defensive: shouldn't normally happen in ARMED */
                env->unregister_code16(st->held_primary);
                st->primary_committed_to_host = false;
            }
            Dyad_dispatch_event(&st->sm, Dyad_EventId_ON_PRIMARY_RELEASE);
            return KBSM_CONSUME;
        }
        return KBSM_PASS;
    }

    return KBSM_PASS;
}

/* No timer-based logic. Dyad decisions are purely event-ordered. */
static void dyad_reset(void *self) {
    dyad_state_t *st = (dyad_state_t *)self;
    Dyad_ctor(&st->sm);
    Dyad_start(&st->sm);
    st->active_dyad_index = -1;
    st->primary_committed_to_host = false;
}

static kbsm_t *machine_get(void) {
    return &g_machine;
}

/* ---- lifecycle ---- */

static uint32_t module_init(kbsm_env_t *env) {
    if (!env) return 0xDEADBEEFu;  /* firmware built without kbsm support */

    g_state.env = env;
    Dyad_ctor(&g_state.sm);
    Dyad_start(&g_state.sm);
    g_state.active_dyad_index = -1;
    g_state.primary_committed_to_host = false;

    g_machine.instance = &g_state;
    g_machine.handle   = dyad_handle;
    g_machine.tick     = NULL;  /* no periodic logic; pure event-driven */
    g_machine.reset    = dyad_reset;
    g_machine.name     = "dyad_sram";
    g_machine.phase    = KBSM_PHASE_PRE_TAP;
    g_machine.priority = 60;  /* below sticky_combo (40) and vim_modal (50) */

    env->kbsm_register(&g_machine);
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
