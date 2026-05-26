/* null_module.c — minimal smoke-test module.
 *
 * Purpose: verify the module load/dispatch mechanism with the smallest
 * possible footprint. Only claims MODULE_HOOK_INIT; every other slot
 * stays NULL so the dispatcher never jumps into this module again
 * after boot.
 *
 * init prints a one-line confirmation via mprintf (a printf-compatible
 * diagnostic helper gated by debug_config_user.module on the device)
 * so the console can show the call made it all the way through the
 * loader into module code once the user enables the gate.
 *
 * If this module loads and prints, the load/dispatch path (Thumb-bit
 * handling, hook-table patching, init_off computation, XIP setup,
 * literal-pool relocation) is working. Any richer module that then
 * hangs is due to its own code or external symbol resolution.
 *
 * Note: passing a plain string literal to mprintf works transparently
 * because the host builder emits an R_ARM_ABS32 reloc for the literal
 * pool slot and the firmware loader rebases it to slot_addr at load
 * time. Module code references its own .rodata through plain C; no
 * load-address arithmetic is needed.
 */

#include "module_api.h"

static uint32_t module_init(void) {
    mprintf("null_module init\n");
    return MODULE_INIT_MAGIC;
}

MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_HOOK_INIT] = module_init,
};
