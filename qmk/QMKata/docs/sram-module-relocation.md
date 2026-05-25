# SRAM Module Relocation

## The Problem

An SRAM module is compiled independently from the firmware, linked against a stub linker script, and loaded at runtime into an arbitrary SRAM address (`g_module_sram`, typically `0x2000F000` or wherever the firmware carve-out lands). The module's `.text` and `.rodata` contain absolute addresses that were correct at compile time (when linked at address 0), but are wrong at runtime (when loaded at the actual SRAM address).

## How Absolute Addresses Get Into the Binary

Consider this C code in a module:

```c
static const char *msg = "hello";
void foo(void) {
    xprintf(msg);          // addr of "hello" in .rodata
    xprintf(0x08012360);   // hardcoded firmware address
}
```

GCC with `-fPIC` emits **position-independent** code for function calls (using PC-relative addressing via `LDR + ADD pc`). But for data symbols — addresses of `.rodata` strings, addresses of global variables, addresses in pointer tables — it emits **absolute 32-bit addresses** with `R_ARM_ABS32` relocation entries in the ELF.

## The Relocation Pipeline

### Step 1 — Build (compile + link)

Module linked at address 0. The `.text` section contains absolute addresses like `0x000007e4` (the compile-time offset of `"hello"` in `.rodata`). The ELF file records these as `R_ARM_ABS32` relocations: "replace the 32-bit value at offset X with (symbol_addr + load_base)."

### Step 2 — Host resolves relocations (qmk-tools ModuleBuild)

The host reads the ELF's relocation table, extracts each `R_ARM_ABS32` entry, and adjusts the 32-bit value in the binary by adding the target slot address.

Example:
- Compile-time value at offset `0x100`: `0x000007E4` (string in .rodata)
- Target slot address (g_module_sram): `0x2000F000`
- Relocated value: `0x000007E4 + 0x2000F000 = 0x2000F7E4`

### Step 3 — Load into SRAM

The firmware's `module_sram_write()` copies the adjusted binary to the SRAM slot. The module's code now references `0x2000F7E4` instead of `0x000007E4` — correct for the runtime address.

### Step 4 — Host recomputes CRC

After applying relocations, the host computes a new CRC-32 over the modified binary and writes it into the `crc32` field of the 32-byte module header. The firmware verifies this CRC on every boot via `module_boot_scan()`.

## The Critical Gap: `.rodata` → `.rodata` Pointers

**GCC does NOT emit `R_ARM_ABS32` relocations for `.rodata`→`.rodata` pointer references.** This is a known limitation discovered during autotext module development.

### Example of the bug

```c
static const autotext_def_t table[] = {
    { "teh", "the" },   // const char *trigger, const char *expansion
};
```

The string literals `"teh"` and `"the"` live in `.rodata` at addresses like `0x000007E4` and `0x000007E8`. These addresses get stored as 32-bit values in the `autotext_def_t` struct (also in `.rodata`).

But **GCC does not mark these as relocatable** — it considers `.rodata`→`.rodata` references as "within the same section, known at link time" and does not emit `R_ARM_ABS32` entries.

When the module loads into SRAM at `0x2000F000`:
- The struct is at `0x2000F000 + offset_of_table`
- The pointer field still holds `0x000007E4` (compile-time address, not runtime address)
- Reading `trigger[0]` at that address returns garbage (it's in firmware flash, not SRAM)

### Symptoms observed during debugging

| Observation | Interpretation |
|---|---|
| `trigger_len = 0` for all triggers | `trigger[0]` is `\0` — reading null at wrong address |
| Pointer value `0x000007E4` | Firmware flash (0x08000000+), not SRAM (0x20000000+) |
| `find_trigger()` always returns -2 | No prefix or exact match possible with len=0 strings |

## The Fix: Inline Char Arrays

Instead of storing pointers, embed the data directly in the struct:

```c
// BROKEN — pointer fields that need relocation but get none
typedef struct {
    const char *trigger;
    const char *expansion;
} autotext_def_t;

// FIXED — inline arrays, no pointers to relocate
typedef struct {
    char trigger[AUTOTEXT_MAX_TRIGGER_LEN];   // 16 bytes
    char expansion[AUTOTEXT_MAX_EXP_LEN];     // 128 bytes
} autotext_def_t;
```

Usage:
```c
static const autotext_def_t table[] = {
    { "teh", "the" },   // string literal initializes the inline char array
};
```

The string data is now part of the struct itself — stored as arrays of bytes, not pointers. The data is copied to SRAM with the struct when the module loads. No pointer indirection, no relocation needed.

**This pattern is used by all kbsm module examples** (sticky_combo, dyad, autotext, holdseq).

## Why Current Modules Show "0 ABS32 Relocs"

```
relocs: 0 ABS32 entries
```

The build output shows zero relocations for our current modules because:
- **Function calls** use PC-relative addressing (`-fPIC`)
- **String data** is embedded in inline char arrays (no pointers)
- **No external firmware symbol references** (all interactions go through `kbsm_env_t`)

The module is **fully position-independent** — it works at any load address without relocation.

## When Relocations ARE Emitted

`R_ARM_ABS32` relocations will appear when:

| Pattern | Relocated? | Example |
|---|---|---|
| External firmware function pointer | Yes | `void (*fn)(void) = some_firmware_function;` |
| `.text` → `.rodata` string address | Yes | `xprintf("hello")` in function body |
| `.rodata` → `.rodata` pointer | **No** | `const char *ptr = "hello"` in a struct |
| `.data` → `.rodata` pointer | **No** | Same as above but in `.data` section |

## Lessons for Module Authors

1. **Never use `const char *` in module data tables.** Use `char name[N]` inline arrays instead.
2. **Assume 0 relocations is the target state** for kbsm SRAM modules. If you see non-zero relocs, audit for pointer fields or external symbol references.
3. **Test with `trigger[0] != 0` early.** If a string field reads as `\0` at runtime when it should be a printable character, you've hit this bug.
4. **The linker script places `.data` and `.bss` in the MODULE region** (not `/DISCARD/`), so writable globals are preserved in SRAM. For flash modules, writable globals are rejected.

## Related

- `docs/sram-module-compilation.md` — compilation pipeline for SRAM modules
- `ModuleBuild.py` — host-side build, relocation, and CRC logic
- `build_sram_module.py` — wrapper script for building SRAM module examples
- `module_api.h` — host-side ABI header (kbsm_env_t callback table)
- `module_loader.h` (firmware) — module header structure and hook indices
