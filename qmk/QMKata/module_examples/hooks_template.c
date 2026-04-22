/*
 * hooks_template.c — API-reference skeleton for loadable modules.
 *
 * Implements every hook defined in module_api.h with:
 *   - the correct signature (matches firmware module_dispatch.c),
 *   - a body that returns the same default the firmware dispatcher
 *     returns when no module claims the hook (so leaving a hook's
 *     skeleton body in place is behaviourally a no-op),
 *   - a printf() trace line so you can confirm on the console that
 *     the firmware is actually calling the hook.
 *
 * Usage:
 *   1. Copy this file, rename, strip out hooks you don't need.
 *   2. Remove the corresponding entries from module_hook_table below.
 *   3. Build + load via the QMKata "modules" tab.
 *
 * Prerequisites for the trace output:
 *   - Firmware built with CONSOLE_ENABLE = yes (so printf is linked
 *     into the firmware's .map and the host builder can resolve it).
 *   - A console reader attached: hid_listen, or the QMKata "console"
 *     tab.
 *
 * Size budget reminder:
 *   - A slot is 4096 bytes. The header (32 B) and hook table (64 B)
 *     consume a fixed 96 B, leaving ~4000 B for code + rodata. The
 *     trace strings below cost a few hundred bytes of .rodata; trim
 *     them if you're close to the ceiling.
 */

#include "module_api.h"

/* printf is provided by the firmware (CONSOLE_ENABLE=yes, via
 * lib/printf/printf.c). The host module builder resolves this symbol
 * against the firmware .map file and emits its absolute address in
 * symbols.ld at link time.
 *
 * Note: QMK's xprintf() is a preprocessor macro that expands to
 * printf(), not a real symbol. Modules must call printf() directly —
 * QMK headers like quantum/logging/print.h are not included here. */
extern int printf(const char *fmt, ...);

/* Local prototypes for init/deinit — module_api.h does not declare
 * them since they are module-local names, not part of the public API. */
static uint32_t module_init(uint32_t module_base);
static uint32_t module_deinit(void);

/* ------------------------------------------------------------------ *
 * Hook implementations
 *
 * Each body:
 *   - emits a trace line tagged [mod] with the hook name and the
 *     arguments most useful for debugging,
 *   - returns the firmware's built-in default (see module_dispatch.c).
 *
 * `combo` pointers are logged as addresses only; dereferencing them
 * to read keycode/keys requires knowing the full QMK combo_t layout,
 * which module_api.h intentionally keeps opaque.
 * ------------------------------------------------------------------ */

/* Index 0 — called for every combo candidate before the combo fires.
 * Return false to suppress this combo; true to allow it. */
bool combo_should_trigger(uint16_t combo_index, combo_t *combo,
                          uint16_t keycode, keyrecord_t *record) {
    (void)combo;
    (void)record;
    printf("[mod] combo_should_trigger idx=%u kc=%u\n", combo_index, keycode);
    return true;
}

/* Index 1 — called after a combo is recognized. `pressed` is true on
 * press, false on release. Return value is void. */
void process_combo_event(uint16_t combo_index, bool pressed) {
    printf("[mod] process_combo_event idx=%u pressed=%u\n",
            combo_index, (unsigned)pressed);
}

/* Index 2 — per-combo override of COMBO_TERM (ms). Return the window
 * within which all combo keys must be pressed. */
uint16_t get_combo_term(uint16_t index, combo_t *combo) {
    (void)combo;
    printf("[mod] get_combo_term idx=%u\n", index);
    return COMBO_TERM;
}

/* Index 3 — module lifecycle: called once, right after the module's
 * hooks are installed in the dispatch table. Use for one-shot setup
 * that doesn't require writable globals (modules have no .data/.bss).
 * Must return MODULE_INIT_MAGIC so the firmware loader can confirm
 * the call reached module code; any other value is logged as a
 * mismatch warning. */
static uint32_t module_init(uint32_t module_base) {
    /* NOTE: To print strings from flash, you must use module_base.
       e.g. printf("%s", (char *)(module_base + OFFSET)); */
    printf("[mod] init (base=0x%lx)\n", (unsigned long)module_base);
    return MODULE_INIT_MAGIC;
}

/* Index 4 — module lifecycle: called once, right before the module's
 * hooks are removed (on unload, or before a replacing module_load).
 * Use for cleanup that does not touch flash. Return value is logged
 * by the firmware but not checked; 0 is conventional. */
static uint32_t module_deinit(void) {
    printf("[mod] deinit\n");
    return 0;
}

/* Index 5 — per-combo "must hold" override. Return true to require
 * the combo keys to be held (not tapped) for the combo to fire. */
bool get_combo_must_hold(uint16_t index, combo_t *combo) {
    (void)combo;
    printf("[mod] get_combo_must_hold idx=%u\n", index);
    return false;
}

/* Index 6 — per-combo "must tap" override. Return true to require
 * the combo keys to be tapped (not held) for the combo to fire. */
bool get_combo_must_tap(uint16_t index, combo_t *combo) {
    (void)combo;
    printf("[mod] get_combo_must_tap idx=%u\n", index);
    return false;
}

/* Index 7 — per-combo "must press in order" override. Return true to
 * require combo keys to be pressed in the order they are declared. */
bool get_combo_must_press_in_order(uint16_t index, combo_t *combo) {
    (void)combo;
    printf("[mod] get_combo_must_press_in_order idx=%u\n", index);
    return true;
}

/* Index 8 — called when a key belonging to an active combo is
 * released. Return true if the module handled the release. */
bool process_combo_key_release(uint16_t index, combo_t *combo,
                               uint8_t key_index, uint16_t keycode) {
    (void)combo;
    printf("[mod] process_combo_key_release idx=%u key=%u kc=%u\n",
            index, key_index, keycode);
    return false;
}

/* Index 9 — called when a key belonging to an active combo is
 * pressed again while the combo is live. Return true if handled. */
bool process_combo_key_repress(uint16_t index, combo_t *combo,
                               uint8_t key_index, uint16_t keycode) {
    (void)combo;
    printf("[mod] process_combo_key_repress idx=%u key=%u kc=%u\n",
            index, key_index, keycode);
    return false;
}

/* Index 10 — remap which combo-definitions layer is consulted for a
 * given active layer. Return the layer whose combos should apply;
 * returning `layer` unchanged means no remapping. */
uint8_t combo_ref_from_layer(uint8_t layer) {
    printf("[mod] combo_ref_from_layer layer=%u\n", layer);
    return layer;
}

/* ------------------------------------------------------------------ *
 * Hook table — 16 entries, one per MODULE_HOOK_* index.
 *
 * Entries the module does not implement should be omitted from this
 * table (C designated initializers leave them NULL, which tells the
 * dispatcher "no module claims this hook").
 * ------------------------------------------------------------------ */
MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_HOOK_COMBO_SHOULD_TRIGGER]          = combo_should_trigger,
    [MODULE_HOOK_PROCESS_COMBO_EVENT]           = process_combo_event,
    [MODULE_HOOK_GET_COMBO_TERM]                = get_combo_term,
    [MODULE_HOOK_INIT]                          = module_init,
    [MODULE_HOOK_DEINIT]                        = module_deinit,
    [MODULE_HOOK_GET_COMBO_MUST_HOLD]           = get_combo_must_hold,
    [MODULE_HOOK_GET_COMBO_MUST_TAP]            = get_combo_must_tap,
    [MODULE_HOOK_GET_COMBO_MUST_PRESS_IN_ORDER] = get_combo_must_press_in_order,
    [MODULE_HOOK_PROCESS_COMBO_KEY_RELEASE]     = process_combo_key_release,
    [MODULE_HOOK_PROCESS_COMBO_KEY_REPRESS]     = process_combo_key_repress,
    [MODULE_HOOK_COMBO_REF_FROM_LAYER]          = combo_ref_from_layer,
};
