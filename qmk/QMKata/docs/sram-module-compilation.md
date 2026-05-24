# SRAM Module Compilation

This document describes how QMKata builds loadable SRAM modules and why
the compilation flags are chosen the way they are. Knowing the rationale
matters because picking the wrong flag combination produces modules that
either crash silently or hang the keyboard, often only at runtime.

If you only want to write a module, see `module_examples/` and the
`module_api.h` API. If you are changing the build pipeline or porting
the loader to a new MCU, read on.

## TL;DR

* Modules are compiled with **`-fPIC`** so that all symbol references go
  through PC-relative addressing.
* Linker script `module_linker.ld` (or a generated variant for SRAM)
  links at **`ORIGIN = 0`**.
* For SRAM modules, `.data` and `.bss` are kept in the binary blob.
* No host-side relocation pass runs against the linked module — the
  binary is uploaded verbatim and the loader writes it to a free SRAM
  slot.
* The module's `module_init(env)` receives `env->module_base` set to the
  slot address. The current sticky-combo example does **not** need to
  use it because `-fPIC` already produces correct runtime addresses;
  `module_base` is provided for future modules that may want to derive
  offsets explicitly.

## Compilation pipeline

`ModuleBuild.build(source_file, target)` orchestrates:

| Step | Action | File / function |
|------|--------|-----------------|
| 1 | Compile `.c` → `.o` with the flag set below | `_compile()` |
| 1.5 | If `target == 'flash'`, reject any module with writable sections (`.data`, `.bss`). SRAM modules skip this check. | `_validate_no_writable_sections()` |
| 2 | Resolve undefined symbols against the firmware `.map` and generate a `symbols.ld` with `PROVIDE(name = 0x...)` for each. | `_resolve_symbols()` |
| 2.5 | For `target == 'sram'`, generate a per-build linker script that *keeps* `.data` and `.bss` in the output (the stock script discards them). | inline in `build()` |
| 3 | Link `.o` + `symbols.ld` against `module_linker.ld` (or the SRAM variant) | `GccToolchain.link()` |
| 4 | `objcopy --output-target=binary` to strip the ELF wrapper. | `GccToolchain.elf2bin()` |
| 5 | Read the raw binary, detect which hooks the module provides, and assemble the final blob (header + hook table + code). | `_assemble()` |

The resulting `result['binary']` is what gets uploaded to the keyboard
via QMKata's MIDI/HID transport.

## Compile flags (`_compile`)

```
-c                              # produce a relocatable object
-mcpu=cortex-m4                 # target MCU
-mthumb                         # Thumb-2 instruction set
-mfloat-abi=hard
-mfpu=fpv4-sp-d16
-Os                             # optimise for size
-ffreestanding                  # no hosted libc assumptions
-ffunction-sections             # each function in its own section so the
-fdata-sections                 # linker can garbage-collect unused ones
-fno-common                     # uninitialised globals get distinct symbols
-fPIC                           # *** see below ***
-fno-unwind-tables              # do not emit .ARM.exidx / .ARM.extab —
-fno-asynchronous-unwind-tables # the linker script discards them, so any
-fno-exceptions                 # generated references would dangle
-Wall -Werror -std=gnu11
```

`-fPIC` is the most important flag and the reason this document exists.

### Why `-fPIC` is load-bearing

A module is compiled and linked at `ORIGIN = 0` but loaded into SRAM at
an address chosen by the firmware (currently `0x20003d68` for slot 8).
Any code that holds a symbol's *absolute link-time address* will read
or jump to the wrong place at runtime.

Without `-fPIC`, GCC on Cortex-M Thumb-2 chooses between several
addressing modes for each symbol reference, often inconsistently within
the same function:

| Compiler choice | Encoding | Value at runtime |
|---|---|---|
| `ADR rX, sym` | PC-relative, 12-bit range | Correct runtime address (good) |
| Literal-pool absolute | `LDR rX,[pc,#N]` where the pool holds the linker-resolved absolute address | The link-time absolute (e.g. `0x470`) — wrong (bad) |
| `MOVW`/`MOVT` pair | 32-bit immediate split across two instructions | The link-time absolute — wrong (bad) |

Because the choice is not predictable, even a single function can
contain a mix: writes to `g_machine.field` might go to one address while
`&g_machine` passed to `kbsm_register()` goes to another. The
module then registers a "machine" pointer that is correctly readable
by the firmware while the module's own writes silently land somewhere
else (often in the peripheral region above `0x40000000`, with no fault
because the writes are valid bus transactions to ignored registers).
The result is a machine struct that the firmware reads as all zeros.

With `-fPIC`, GCC settles on a single, position-independent pattern
for *every* symbol reference. On Cortex-M Thumb-2 that pattern is the
**GOT-less PIC sequence**:

```asm
ldr  rX, [pc, #N]      ; load a PC-delta from the literal pool
add  rX, pc            ; rX = (pc + 4 of the LDR) + delta = sym
```

Because the literal pool stores a delta to `sym` (not `sym` itself),
the computation gives the correct runtime SRAM address at any load
offset. No host-side relocation pass and no runtime rebasing in the
module is required.

GCC chooses this sequence even though we link as `ET_EXEC` rather than
`ET_DYN` / PIE. Linking as `-pie` was tried first but fails on
bare-metal because the linker insists on a PHDR/LOAD segment
arrangement that does not fit our flat linker script. `-shared` was
also tried; it produces ET_DYN but emits GOT-relative loads that
require an initialised `r9` / GOT pointer at runtime, which we do not
have. Plain `ET_EXEC` with `-fPIC` is the right combination.

### Why we no longer rebase on the host

Earlier iterations of `ModuleBuild` extracted `R_ARM_ABS32` relocations
from the linked ELF and patched the binary at upload time by adding
`slot_addr` to each literal-pool entry. With `-fPIC` the compiler emits
no such absolute literal-pool entries in the first place, so there is
nothing left to rebase. The relocation-extraction code is kept in
`ModuleBuild._extract_relocations()` for legacy / future compatibility,
but `apply_relocations_and_crc()` is a no-op when the list is empty,
which is the steady state today.

## Linker script

`module_linker.ld` defines a single read/execute region:

```ld
MEMORY {
    MODULE (rx) : ORIGIN = 0, LENGTH = 0x1000
}
SECTIONS {
    .module_header : { LONG(0) ... }  > MODULE  /* 32-byte hole filled by ModuleBuild */
    .hook_table    : ALIGN(4) { *(.hook_table) } > MODULE
    .text          : ALIGN(4) { *(.text*) *(.rodata*) } > MODULE
    /DISCARD/      : { *(.data*) *(.bss*) ... }  /* flash variant */
}
```

For SRAM builds the discard rule is replaced (in
`ModuleBuild.build()`) with explicit output sections that keep `.data`
and `.bss` inside the MODULE region, so the binary blob contains
zero-initialised state slots that the firmware writes into SRAM along
with the code.

`.rodata` is merged into `.text` for PC-relative reachability — the
GOT-less `LDR + ADD pc` sequence used by `-fPIC` can only reach a
limited PC offset, and keeping code and read-only data contiguous keeps
every string literal within range.

## Host upload + firmware loader

The module binary layout, as built by `_assemble()`:

```
+----------------------------+ offset 0
| module_header_t (32 bytes) |
+----------------------------+
| hook_table (uint32_t[MAX]) |
+----------------------------+
| .text + .rodata            |
+----------------------------+
| .data (SRAM target only)   |
+----------------------------+
| .bss  (SRAM target only)   |
+----------------------------+
```

On the firmware side, `module_loader.c`:

1. Validates the header (magic / version / size / hook bitmap / CRC).
2. For SRAM target, picks a free SRAM slot, copies the blob there
   verbatim, and emits `DSB` / `ISB` to make the bytes visible to the
   instruction fetcher.
3. Claims hook entries by storing the slot's `slot_addr + hook_offset`
   (with the Thumb bit set) into `g_module_hooks[]`.
4. Sets `env->module_base = slot_addr` and calls
   `init_fn(env)`. The init function lives in the module at offset
   `header.init_off`, and the loader computes its address as
   `slot_addr + init_off | 1` (the `| 1` is the Thumb-bit invariant).
5. Returns `true` to the host once `init` returns `MODULE_INIT_MAGIC`.

The `env->module_base` value is currently informational. The example
sticky-combo module ignores it because `-fPIC` already produces correct
runtime pointers. A future module that wants to perform its own
explicit pointer arithmetic (for example to compute an address that the
compiler refuses to materialise via the PIC sequence) can add
`env->module_base` to a link-time offset and obtain the runtime
absolute address.

## Verifying the compiled output

Useful one-liners on a built ELF (the temporary file is in
`tempfile.TemporaryDirectory(prefix="module_build_")`; preserve it by
running the build under `KEEP_TMP=1` or copy the path from a
`ModuleBuild.last_error` debug print):

```sh
arm-none-eabi-readelf -h module.elf       # ELF type must be EXEC
arm-none-eabi-nm module.elf | sort        # check symbol layout
arm-none-eabi-objdump -d --disassemble=module_init module.elf
arm-none-eabi-objdump -r module.elf       # remaining relocations — should be empty
```

In `module_init` disassembly you should see the `LDR + ADD pc` pattern
for every reference to `g_machine`, `g_state`, `sticky_handle`, etc.
If you see `MOVW` / `MOVT` immediates or a bare `LDR rX,[pc,#N]`
without a following `ADD rX,pc`, something has gone wrong with the
flags — the resulting module will not work at the SRAM load address.

## Why not the alternatives

| Approach | Status | Reason rejected |
|---|---|---|
| `-fPIC` + `-pie` link | ✗ | Linker errors: "PHDR segment not covered by LOAD segment" on bare-metal flat layout. |
| `-fPIC` + `-shared` link | ✗ | Produces ET_DYN with GOT-relative loads; requires a runtime linker / `r9` GOT pointer that bare-metal does not provide. |
| No `-fPIC`, host rebases R_ARM_ABS32 relocs | ✗ | Linker resolves everything at link time for ET_EXEC; the output ELF has no remaining ABS32 relocations to extract. |
| No `-fPIC`, module rebases pointers manually using `env->module_base` | ✗ | The compiler uses ADR for some symbols and literal-pool-absolute for others, *inconsistently*, so adding `module_base` is right for half the references and wrong for the rest. |
| `-fPIC` + ET_EXEC link (current) | ✓ | Compiler settles on the GOT-less PIC sequence uniformly; addresses are correct at any load offset without any rebasing. |

## Related files

* `qmk/QMKata/ModuleBuild.py` — build pipeline
* `qmk/QMKata/GccToolchain.py` — wraps `gcc` / `ld` / `objcopy` invocations
* `qmk/QMKata/module_linker.ld` — linker script
* `qmk/QMKata/module_api.h` — module-side API (`kbsm_env_t`, hook IDs)
* `qmk/QMKata/module_examples/kbsm_sticky_combo/` — working SRAM module
* `keyboards/keychron/common/module/module_loader.c` — firmware loader
* `keyboards/keychron/common/module/kbsm_env.c` — firmware env table

## Sticky-combo state-machine fix (resolved)

The sticky-combo module had a bug where the first key of a combo was
leaked to the host before the module knew whether the partner key would
follow within the window. This was fixed by deferring the first press
(via `SM_CONSUME`) and flushing on window expiry or third-key arrival.
The same fix was applied to both the SRAM module and the firmware-built
adapter. See `docs/plans/sticky-combo-fix.md` for the full analysis.
