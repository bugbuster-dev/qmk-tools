/* Module linker script - links at base 0 for slot-independent modules */
MEMORY {
    MODULE (rx) : ORIGIN = 0, LENGTH = 0x1000
}
SECTIONS {
    .module_header : {
        /* Emit 40 real bytes so objcopy keeps header padding in the raw binary. */
        LONG(0) LONG(0) LONG(0) LONG(0) LONG(0)
        LONG(0) LONG(0) LONG(0) LONG(0) LONG(0)
    } > MODULE
    .hook_table : ALIGN(4) {
        KEEP(*(.hook_table))
        . = ALIGN(4);
        . = 40 + 64;  /* Force hook table to end at offset 104 (40-byte header + 64-byte table) */
    } > MODULE
    .text : ALIGN(4) {
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > MODULE
    /DISCARD/ : {
        *(.data*)
        *(.bss*)
        *(.comment)
        *(.ARM.attributes)
        *(.ARM.exidx*)
        *(.ARM.extab*)
        *(.eh_frame*)
        *(.gnu.linkonce.armexidx.*)
    }
}
