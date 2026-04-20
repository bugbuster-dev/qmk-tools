/* Module linker script - links at base 0 for slot-independent modules */
MEMORY {
    MODULE (rx) : ORIGIN = 0, LENGTH = 0x1000
}
SECTIONS {
    .module_header : {
        . = 32;  /* Reserve space for 32-byte header (host fills post-link) */
    } > MODULE
    .hook_table : ALIGN(4) {
        KEEP(*(.hook_table))
        . = ALIGN(4);
        . = 32 + 64;  /* Force hook table to end at offset 96 (32-byte header + 64-byte table) */
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
    }
}
