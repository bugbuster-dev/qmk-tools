/* null_module.c — minimal smoke-test module.
 *
 * Purpose: verify the module load/dispatch mechanism with the smallest
 * possible footprint. Only claims MODULE_HOOK_INIT; every other slot
 * stays NULL so the dispatcher never jumps into this module again
 * after boot.
 *
 * init prints a one-line confirmation via the firmware's printf (same
 * mechanism hooks_template uses) so the console shows the call made it
 * all the way through the loader into module code.
 *
 * If this module loads and prints, the load/dispatch path (Thumb-bit
 * handling, hook-table patching, init_off computation, XIP setup) is
 * working. Any richer module that then hangs is due to its own code
 * or external symbol resolution.
 */

#include "module_api.h"
 
/* printf is provided by the firmware (CONSOLE_ENABLE=yes). Host module
 * builder resolves this symbol against the firmware .map and emits its
 * absolute address in symbols.ld at link time. */
extern int printf(const char *fmt, ...);
 
/* This string is placed in .rodata. Because the module is linked at base 0,
 * the symbol address is exactly its offset from the module base. */
static const char init_msg[] = "[mod] null_module init\n";
 
/* Marked used so the compiler can't optimize it away; the linker would
 * otherwise drop an unreferenced static function. The hook table below
 * references it, but -ffunction-sections + gc-sections has bitten us
 * before.
 *
 * Returns MODULE_INIT_MAGIC so the firmware loader can confirm the
 * call reached module code and ran to completion end-to-end. Any
 * other return value causes the loader to log a mismatch warning. */
static uint32_t module_init(uint32_t module_base) __attribute__((used));
static uint32_t module_init(uint32_t module_base) {
    /* Access the string by adding its link-time offset to the runtime base.
       This avoids the absolute literal pool trap. */
    printf("%s", (const char *)(module_base + (uintptr_t)init_msg));
    return MODULE_INIT_MAGIC;
}
 
MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_HOOK_INIT] = module_init,
};
