/*
 * Linker script for dynld animations — ModuleBuild pipeline,
 * but without kbsm header/hook table. .text goes at offset 0.
 *
 * Based on module_linker.ld, stripped of .module_header and .hook_table.
 * The resulting binary goes directly into dynld_func_buf[] and is
 * executed from byte 0 by the firmware's SysEx handler.
 *
 * .data and .bss are kept in the MODULE region so static variables
 * work. -fPIC ensures PC-relative addressing stays valid since code
 * and data move together in the same RAM buffer.
 */

ENTRY(effect_runner_func)

MEMORY
{
    MODULE (rwx) : ORIGIN = 0, LENGTH = 0x1000
}

SECTIONS
{
    .text : ALIGN(4)
    {
        *(.text.entry)
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > MODULE

    .data : ALIGN(4)
    {
        *(.data*)
        . = ALIGN(4);
    } > MODULE

    .bss : ALIGN(4)
    {
        *(.bss*)
        . = ALIGN(4);
    } > MODULE

    /DISCARD/ :
    {
        *(.ARM.exidx*)
        *(.ARM.extab*)
        *(.gnu*)
        *(.note*)
        *(.eh_frame*)
        *(.comment*)
    }

    . = ALIGN(4);
}
