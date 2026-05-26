/* kbsm_vim_modal — SRAM-loadable vim modal layer module.
 *
 * Ported from quantum/features/vim_modal_adapter.c to use kbsm_env_t.
 * 5 vim modes: Normal, Insert, Visual, Command, Replace.
 * Escape always returns to Normal. Insert passes keys through.
 *
 * Always active when loaded. Unload to disable.
 * Priority 50 — runs before dyad (60), holdseq (65), autotext (70).
 */

#include "module_api.h"
#include "VimModal.h"
#include "VimModal.c"
#include "vim_modal_def.h"

typedef struct {
    VimModal sm;
    kbsm_env_t *env;
} vim_modal_state_t;

static vim_modal_state_t g_state;
static kbsm_t g_machine;

/* Check if a key event matches Escape by either keycode or physical position.
 * Needed when Esc is bound to a tap-dance or other quantum keycode — in that
 * case get_record_keycode() returns the quantum keycode (e.g. TD(x)), not KC_ESC.
 * The physical row/col fallback is configured via VIM_ESC_ROW / VIM_ESC_COL. */
static bool is_esc(uint16_t kc, keyrecord_t *r) {
    if (kc == KC_ESC) return true;
    return (r->event.key.row == VIM_ESC_ROW && r->event.key.col == VIM_ESC_COL);
}

static kbsm_result_t handle_normal(vim_modal_state_t *st, uint16_t kc, keyrecord_t *r) {
    if (!r->event.pressed) return KBSM_CONSUME;
    kbsm_env_t *env = st->env;

    switch (kc) {
        case KC_I:
            VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_I);
            return KBSM_CONSUME;
        case KC_A:
            env->tap_code(KC_RIGHT);
            VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_A);
            return KBSM_CONSUME;
        case KC_O:
            env->tap_code(KC_END);
            env->tap_code(KC_ENTER);
            VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_O);
            return KBSM_CONSUME;
        case KC_V:
            VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_V);
            return KBSM_CONSUME;
        case KC_H: env->tap_code(KC_LEFT);  return KBSM_CONSUME;
        case KC_J: env->tap_code(KC_DOWN);  return KBSM_CONSUME;
        case KC_K: env->tap_code(KC_UP);    return KBSM_CONSUME;
        case KC_L: env->tap_code(KC_RIGHT); return KBSM_CONSUME;
        case KC_W: env->tap_code16(LCTL(KC_RIGHT)); return KBSM_CONSUME;
        case KC_B: env->tap_code16(LCTL(KC_LEFT));  return KBSM_CONSUME;
        case KC_0: env->tap_code(KC_HOME); return KBSM_CONSUME;
        case KC_DOT: env->tap_code(KC_END); return KBSM_CONSUME;
        case KC_G: env->tap_code16(LCTL(KC_HOME)); return KBSM_CONSUME;
        case KC_X: env->tap_code(KC_DEL);  return KBSM_CONSUME;
        case KC_U: env->tap_code16(LCTL(KC_Z)); return KBSM_CONSUME;
        case KC_R: env->tap_code16(LCTL(KC_Y)); return KBSM_CONSUME;
        case KC_P: env->tap_code16(LCTL(KC_V)); return KBSM_CONSUME;
        case KC_Y: env->tap_code16(LCTL(KC_C)); return KBSM_CONSUME;
        default:   return KBSM_CONSUME;
    }
}

static kbsm_result_t handle_insert(vim_modal_state_t *st, uint16_t kc, keyrecord_t *r) {
    if (is_esc(kc, r) && r->event.pressed) {
        VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_ESCAPE);
        return KBSM_CONSUME;
    }
    return KBSM_PASS;
}

static kbsm_result_t handle_visual(vim_modal_state_t *st, uint16_t kc, keyrecord_t *r) {
    if (!r->event.pressed) return KBSM_CONSUME;
    kbsm_env_t *env = st->env;

    if (is_esc(kc, r)) {
        VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_ESCAPE);
        return KBSM_CONSUME;
    }

    switch (kc) {
        case KC_H: env->tap_code16(LSFT(KC_LEFT));  return KBSM_CONSUME;
        case KC_J: env->tap_code16(LSFT(KC_DOWN));  return KBSM_CONSUME;
        case KC_K: env->tap_code16(LSFT(KC_UP));    return KBSM_CONSUME;
        case KC_L: env->tap_code16(LSFT(KC_RIGHT)); return KBSM_CONSUME;
        case KC_W: env->tap_code16(LSFT(LCTL(KC_RIGHT))); return KBSM_CONSUME;
        case KC_B: env->tap_code16(LSFT(LCTL(KC_LEFT)));  return KBSM_CONSUME;
        case KC_Y:
            env->tap_code16(LCTL(KC_C));
            VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_ESCAPE);
            return KBSM_CONSUME;
        case KC_D:
            env->tap_code16(LCTL(KC_X));
            VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_ESCAPE);
            return KBSM_CONSUME;
        default: return KBSM_CONSUME;
    }
}

static kbsm_result_t handle_command(vim_modal_state_t *st, uint16_t kc, keyrecord_t *r) {
    if (!r->event.pressed) return KBSM_CONSUME;
    if (is_esc(kc, r)) {
        VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_ESCAPE);
    } else if (kc == KC_ENTER) {
        VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_ENTER);
    }
    return KBSM_CONSUME;
}

static kbsm_result_t handle_replace(vim_modal_state_t *st, uint16_t kc, keyrecord_t *r) {
    if (!r->event.pressed) return KBSM_CONSUME;
    if (is_esc(kc, r)) {
        VimModal_dispatch_event(&st->sm, VimModal_EventId_ON_ESCAPE);
        return KBSM_CONSUME;
    }
    st->env->tap_code(KC_DEL);
    return KBSM_PASS;
}

static kbsm_result_t vim_modal_handle(void *self, keyevent_t *event, keyrecord_t *record) {
    vim_modal_state_t *st = (vim_modal_state_t *)self;
    uint16_t kc = st->env->get_record_keycode(record, true);

    switch (st->sm.state_id) {
        case VimModal_StateId_NORMAL:  return handle_normal(st, kc, record);
        case VimModal_StateId_INSERT:  return handle_insert(st, kc, record);
        case VimModal_StateId_VISUAL:  return handle_visual(st, kc, record);
        case VimModal_StateId_COMMAND: return handle_command(st, kc, record);
        case VimModal_StateId_REPLACE: return handle_replace(st, kc, record);
        default: return KBSM_PASS;
    }
}

static void vim_modal_reset(void *self) {
    vim_modal_state_t *st = (vim_modal_state_t *)self;
    VimModal_ctor(&st->sm);
    VimModal_start(&st->sm);
}

static kbsm_t *machine_get(void) { return &g_machine; }

static uint32_t module_init(kbsm_env_t *env) {
    if (!env) return 0xDEADBEEFu;

    g_state.env = env;
    VimModal_ctor(&g_state.sm);
    VimModal_start(&g_state.sm);

    g_machine.instance = &g_state;
    g_machine.handle   = vim_modal_handle;
    g_machine.tick     = NULL;
    g_machine.reset    = vim_modal_reset;
    g_machine.name     = "vim_modal_sram";
    g_machine.phase    = KBSM_PHASE_PRE_TAP;
    g_machine.priority = 50;

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
