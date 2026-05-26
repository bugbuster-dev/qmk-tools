/*
 * Linker script for dynld animations — ModuleBuild pipeline,
 * but without kbsm header/hook table. .text goes at offset 0.
 *
 * Based on module_linker.ld, stripped of .module_header and .hook_table.
 * The resulting binary goes directly into dynld_func_buf[] and is
 * executed from byte 0 by the firmware's SysEx handler.
 */

ENTRY(effect_runner_func)

MEMORY
{
    MODULE (rx) : ORIGIN = 0, LENGTH = 0x1000
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

    /DISCARD/ :
    {
        *(.ARM.exidx*)
        *(.ARM.extab*)
        *(.gnu*)
        *(.note*)
        *(.eh_frame*)
        *(.comment*)
        *(.data*)
        *(.bss*)
    }

    . = ALIGN(4);
}
