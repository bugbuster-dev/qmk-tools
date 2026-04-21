/* null_module.c — minimal smoke-test module.
 *
 * Purpose: verify the module load/dispatch mechanism itself without any
 * external symbol dependencies, library calls, or non-trivial code paths.
 *
 *   - References no firmware symbols (no printf, no layer_state, etc.)
 *   - Only claims MODULE_HOOK_INIT; every other slot stays NULL so the
 *     dispatcher never jumps into this module again after boot.
 *   - module_init() does literally nothing and returns.
 *
 * If uploading and booting this module hangs the keyboard, the fault is
 * in the load/dispatch path (Thumb-bit handling, hook-table patching,
 * init_off computation, XIP setup) — not in any module's own code.
 *
 * If this module runs cleanly and a richer module (hooks_template.c)
 * hangs, the fault is in the richer module's code or its external
 * symbol resolution.
 */

#include "module_api.h"

/* Marked used so the compiler can't optimize it away; the linker would
 * otherwise drop an unreferenced static function. The hook table below
 * references it, but -ffunction-sections + gc-sections has bitten us
 * before. */
static void module_init(void) __attribute__((used));
static void module_init(void) {
    /* Intentionally empty. */
}

MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_HOOK_INIT] = module_init,
};
