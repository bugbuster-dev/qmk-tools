/* Module linker script - links at base 0 for slot-independent modules */
MEMORY {
    MODULE (rx) : ORIGIN = 0, LENGTH = 0x1000
}
SECTIONS {
    .module_header : {
        /* Emit 32 real bytes so objcopy keeps header padding in the raw binary. */
        LONG(0) LONG(0) LONG(0) LONG(0)
        LONG(0) LONG(0) LONG(0) LONG(0)
    } > MODULE
    .hook_table : ALIGN(4) {
        KEEP(*(.hook_table))
        . = ALIGN(4);
        . = 40 + 64;  /* Force hook table to end at offset 104 (40-byte header + 64-byte table) */
    } > MODULE
    .text : ALIGN(4) {
        *(.text*)
        /* NOTE: ModuleBuild._extract_relocations (qmk-tools) filters
           R_ARM_ABS32 entries to .text-targeted ones only. Keeping
           .rodata merged into .text here is a load-bearing invariant:
           moving string literals (or any other rodata) into a separate
           section would make the extractor drop their ABS32 relocs,
           which in turn would leave the firmware loader with no way to
           rebase their literal-pool addresses — silently breaking
           printf("literal") and every other rodata reference at runtime. */
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
