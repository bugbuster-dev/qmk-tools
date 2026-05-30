# SRAM Module Relocation

## The Problem

An SRAM module is compiled independently from the firmware, linked at
`ORIGIN = 0`, and loaded at runtime into a SRAM slot whose actual address
is the firmware's `g_module_sram` symbol. Any absolute link-time address
left in the module would point near `0x00000000` instead of the runtime
SRAM address.

## Current Model: Avoid Absolute Addresses

Current kbsm SRAM modules are compiled with `-fPIC`. On Cortex-M Thumb-2,
GCC emits PC-relative `LDR + ADD pc` sequences for internal function and
data references, so references to `g_state`, `g_machine`, string literals,
and generated StateSmith functions resolve correctly at any SRAM load
address.

The expected build output for these modules is:

```text
relocs: 0 ABS32 entries
```

The host still runs `ModuleBuild.apply_relocations_and_crc()` before
upload/load. With zero relocations this step only sets load flags and
recomputes the final CRC. If future code produces `R_ARM_ABS32` entries,
the host can rebase the extracted offsets against the target slot address,
but zero relocations remains the target state for kbsm modules.

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

When the module loads into SRAM at example address `0x2000F000`:
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

**This pattern is used by all kbsm module examples** (sticky_combo, dyad, autotext, holdseq, vim_modal).

## Why Current Modules Show "0 ABS32 Relocs"

```
relocs: 0 ABS32 entries
```

The build output shows zero relocations for our current modules because:
- **Function calls** use PC-relative addressing (`-fPIC`)
- **String data** is embedded in inline char arrays (no pointers)
- **No external firmware symbol references** (all interactions go through `kbsm_env_t`)

The module is **fully position-independent** — it works at any load address without relocation.

## Relocation Audit Cases

Current kbsm modules should show `0 ABS32 entries`. If the build reports a
non-zero count, inspect why before loading it:

| Pattern | Expected result | Example |
|---|---|---|
| Internal code/data references with `-fPIC` | No ABS32; PC-relative | `g_state`, `g_machine`, generated SM functions |
| Inline char arrays | No pointers to relocate | `char trigger[16]` inside a config struct |
| `.rodata` → `.rodata` pointer | **Broken: no relocation emitted even though one would be needed** | `const char *ptr = "hello"` in a struct |
| `.data` → `.rodata` pointer | **Broken for the same reason** | Pointer field initialized to a string literal |
| External symbol address stored as data | May emit ABS32; audit carefully | `void (*fn)(void) = some_firmware_function;` |

## Lessons for Module Authors

1. **Never use `const char *` in module data tables.** Use `char name[N]` inline arrays instead.
2. **Assume 0 relocations is the target state** for kbsm SRAM modules. If you see non-zero relocs, audit for pointer fields or external symbol references.
3. **Test with `trigger[0] != 0` early.** If a string field reads as `\0` at runtime when it should be a printable character, you've hit this bug.
4. **The linker script places `.data` and `.bss` in the MODULE region** (not `/DISCARD/`), so writable globals have storage in SRAM. `.bss` is not C-runtime-zeroed; initialize runtime fields in `module_init()`. For flash modules, writable globals are rejected.

## Related

- `docs/sram-module-compilation.md` — compilation pipeline for SRAM modules
- `ModuleBuild.py` — host-side build, relocation, and CRC logic
- `build_sram_module.py` — wrapper script for building SRAM module examples
- `module_api.h` — host-side ABI header (kbsm_env_t callback table)
- `module_loader.h` (firmware) — module header structure and hook indices
