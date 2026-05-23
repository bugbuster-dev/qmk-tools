<!-- markdownlint-disable-file -->

# Task Research Notes: ELF Relocation Design Document Corrections

## Research Executed

### File Analysis

- `docs/plans/2026-03-30-elf-relocation-design.md`
  - Current design document with 6 critical technical errors identified
- `docs/plans/2026-03-29-full-elf-loading-design.md`
  - Prior design with correct SRAM addresses and MEL blob format, but wrong relocation type constants (7 and 25 instead of 10 and 30)
- `docs/plans/2026-03-29-elf-loading.md`
  - Prior implementation plan with task breakdown, also has wrong relocation type constants
- `GccToolchain.py`
  - Current ELF handling: `GccElfFile` only extracts `.text` and `.rodata` sections via name-based splitting
- `GccMapfile.py`
  - Map file parser: `functions` dict keyed by symbol name, value has `address`, `size`, `section`, `object_file`
  - `fun_addr(name)` returns `int(self.functions[name]['address'])`
- `QMKataKeyboard.py` (lines 344-376)
  - Current `compile()` returns `{'elf': bytes, 'bin': bytes}` dict
  - Current `exec()` handles `str` (compile+exec) and `bytes` (load+exec) modes

### External Research

- #fetch:https://github.com/ARM-software/abi-aa/blob/main/aaelf32/aaelf32.rst
  - **Authoritative ARM ELF specification** (AAELF32, 2025Q4, released 23 Jan 2026)
  - Confirmed: ARM 32-bit ELF uses REL format (8 bytes: r_offset + r_info), NOT RELA
  - r_info encoding: `type = r_info & 0xFF`, `sym_index = r_info >> 8`
  - Relocation formulas use: S (symbol value), A (addend), T (thumb bit), P (place)
- #fetch:https://raw.githubusercontent.com/llvm/llvm-project/main/lld/ELF/Arch/ARM.cpp
  - **Complete LLVM lld implementation** of all ARM relocation types
  - Contains exact bit manipulation for THM_CALL, THM_JUMP24, ABS32, MOVW/MOVT
  - Contains implicit addend extraction for REL-type relocations
- pyelftools v0.32 installed; verified `ENUM_RELOC_TYPE_ARM` constants match ARM spec exactly

### Verified ARM Relocation Type Constants

| Name | Correct Value | Wrong Value in 2026-03-29 Design | Instruction | Result Mask |
|------|:---:|:---:|---|---|
| `R_ARM_ABS32` | **2** | 2 (correct) | Data (32-bit word) | `(S + A) \| T` |
| `R_ARM_THM_CALL` | **10** | 7 (WRONG - that's `R_ARM_THM_ABS5`) | BL (Thumb-2) | `((S + A) \| T) - P`, mask `0x01FFFFFE` |
| `R_ARM_THM_JUMP24` | **30** | 25 (WRONG - that's `R_ARM_BASE_PREL`) | B.W (Thumb-2) | `((S + A) \| T) - P`, mask `0x01FFFFFE` |

Additional relocation types that may appear with `-fPIC` Thumb-2 code:
| `R_ARM_THM_MOVW_ABS_NC` | **47** | n/a | MOVW (Thumb-2) | `(S + A) & 0x0000FFFF` |
| `R_ARM_THM_MOVT_ABS` | **48** | n/a | MOVT (Thumb-2) | `((S + A) >> 16) & 0xFFFF` |

### Project Conventions

- Standards referenced: ARM AAELF32 specification, pyelftools v0.32 enum values, LLVM lld ARM.cpp
- Instructions followed: Existing project design documents, `GccMapfile.py` API

## Key Discoveries

### 1. REL vs RELA Format (Critical Error in Design)

**The 2026-03-30 design is WRONG.** ARM 32-bit ELF uses `.rel.*` sections (NOT `.rela.*`).

Each relocation entry is **8 bytes** (not 12):
```
struct Elf32_Rel {
    Elf32_Addr r_offset;   // 4 bytes: offset in section where to patch
    Elf32_Word r_info;     // 4 bytes: symbol index (upper 24 bits) + type (lower 8 bits)
};
// No addend field! Addend is implicit (read from the patch location).
```

**Extracting fields from r_info:**
```python
rel_type  = r_info & 0xFF         # lower 8 bits
sym_index = r_info >> 8           # upper 24 bits
```

**Implicit addend:** Read from the bytes at the relocation offset BEFORE patching.
Each relocation type has its own addend extraction logic (see Section 5 below).

### 2. Thumb-2 BL Instruction Encoding (Critical for THM_CALL/THM_JUMP24 Patching)

Thumb-2 BL is a 32-bit instruction stored as two 16-bit half-words (little-endian):

```
First half-word (at offset):     11110 S imm10
Second half-word (at offset+2):  11 J1 1 J2 imm11

Where:
  S     = sign bit
  I1    = NOT(J1 XOR S)    -- note the XOR-NOT encoding!
  I2    = NOT(J2 XOR S)
  offset = SignExtend(S:I1:I2:imm10:imm11:0)

Range: +/- 16 MiB (25-bit signed, halfword-aligned)
```

**Key insight:** J1/J2 are NOT the same as I1/I2. The encoding uses `J1 = NOT(I1 XOR S)`.
This is the "J1J2 branch encoding" used on ARMv7 and later (Cortex-M4 supports this).

### 3. Complete Relocation Patching Logic (from LLVM lld)

**R_ARM_ABS32 (type 2):** Simple 32-bit absolute address
```python
def patch_abs32(data: bytearray, offset: int, val: int):
    """val = (S + A) | T where A = implicit addend (current 32-bit value at offset)"""
    struct.pack_into('<I', data, offset, val & 0xFFFFFFFF)
```

**R_ARM_THM_CALL (type 10) / R_ARM_THM_JUMP24 (type 30):**
PC-relative branch with Thumb-2 encoding.

```python
def patch_thm_call_or_jump24(data: bytearray, offset: int, val: int):
    """
    val = ((S + A) | T) - P
    where P = address of the relocation site (section_base + offset)
    
    Encoding: S:I1:I2:imm10:imm11:0
    Store as two 16-bit half-words with J1/J2 XOR-NOT encoding.
    """
    # val is a signed offset, already computed as target - P
    # Check range: must fit in 25 bits signed (±16 MiB)
    assert -(1 << 24) <= val < (1 << 24), f"Branch out of range: {val}"
    
    hi = read16(data, offset)
    lo = read16(data, offset + 2)
    
    # Encode into first half-word: preserve opcode bits, set S and imm10
    hi = (0xf000 |                      # opcode
          ((val >> 14) & 0x0400) |      # S
          ((val >> 12) & 0x03ff))       # imm10
    
    # Encode into second half-word: preserve opcode bits (BL vs BLX), set J1/J2/imm11
    lo = ((lo & 0xd000) |                                    # opcode (preserves BL bit 12)
          (((~(val >> 10)) ^ (val >> 11)) & 0x2000) |       # J1
          (((~(val >> 11)) ^ (val >> 13)) & 0x0800) |       # J2
          ((val >> 1) & 0x07ff))                             # imm11
    
    write16(data, offset, hi)
    write16(data, offset + 2, lo)
```

**Implicit addend extraction for THM_CALL/THM_JUMP24:**
```python
def get_implicit_addend_thm_branch(data: bytearray, offset: int) -> int:
    """Extract implicit addend from existing BL/B.W instruction."""
    hi = read16(data, offset)
    lo = read16(data, offset + 2)
    
    # Decode: S:I1:I2:imm10:imm11:0
    # I1 = NOT(J1 XOR S), I2 = NOT(J2 XOR S)
    raw = (((hi & 0x0400) << 14) |                       # S
           (~((lo ^ (hi << 3)) << 10) & 0x00800000) |    # I1
           (~((lo ^ (hi << 1)) << 11) & 0x00400000) |    # I2
           ((hi & 0x003ff) << 12) |                       # imm10
           ((lo & 0x007ff) << 1))                         # imm11:0
    
    # Sign extend from 24 bits
    return sign_extend(raw, 24)
```

**Helper functions:**
```python
def read16(data: bytearray, offset: int) -> int:
    return struct.unpack_from('<H', data, offset)[0]

def write16(data: bytearray, offset: int, val: int):
    struct.pack_into('<H', data, offset, val & 0xFFFF)

def sign_extend(val: int, bits: int) -> int:
    """Sign extend a value from 'bits' width to Python int."""
    if val & (1 << (bits - 1)):
        val -= (1 << bits)
    return val
```

### 4. Memory Placement (Critical Error in Design)

**WRONG in 2026-03-30 design:**
```python
# WRONG: 0x08000000 is Flash - cannot execute dynamically loaded code from Flash!
SECTION_BASE_ADDRESSES = {
    '.text': 0x08000000,  # Flash - WRONG!
    '.rodata': 0x08001000, # Flash - WRONG!
```

**CORRECT (from 2026-03-29 design):**
All dynamically loaded sections go into **SRAM** (0x2000xxxx). The firmware pre-allocates
buffers in SRAM, and the Python host must know their exact addresses (from the map file)
to calculate correct relocation targets.

```python
# Correct: from keyboard model config, addresses come from map file
DYNLD_BUFFER_ADDRESSES = {
    'text':   0x20010000,   # SRAM - executable
    'data':   0x20012000,   # SRAM - read/write
    'rodata': 0x20013000,   # SRAM - read only
    'bss':    0x20014000,   # SRAM - zeroed
}
```

### 5. Firmware Handler Endianness Bug

**WRONG in 2026-03-30 design (big-endian byte order):**
```c
uint16_t fun_id = (msg[1] << 8) | msg[2];  // BIG endian!
```

**CORRECT (little-endian, matching Cortex-M4 and protocol spec):**
```c
uint16_t fun_id = msg[1] | (msg[2] << 8);  // LITTLE endian
```

The 2026-03-29 design gets this right:
```c
uint16_t func_id = data[0] | (data[1] << 8);  // Correct LE
```

### 6. Internal Relocation Handling

For functions within the same compilation unit calling each other (e.g., func_a calls func_b),
the linker emits relocations with symbols that are **defined within the ELF** (not external).

Resolution algorithm:
1. Look up symbol in the ELF's own symbol table
2. If `st_shndx != SHN_UNDEF`: internal symbol. Its value = offset within the section.
3. Final address = `section_load_address + symbol.st_value`
4. For `.text` symbols: `final_addr = DYNLD_BUFFER_ADDRESSES['text'] + symbol.st_value`
5. Apply THUMB bit (|1) for function symbols

This requires knowing the final load address of each section BEFORE applying relocations.

### 7. Complete Resolution Algorithm

```python
def resolve_relocations(elf_path: str, mapfile: GccMapfile, 
                        buffer_addresses: dict) -> dict:
    """
    Parse ELF, resolve all relocations, return patched section data.
    
    Args:
        elf_path: Path to .elf file
        mapfile: Parsed firmware map file for external symbol lookup
        buffer_addresses: Dict of section_name -> load_address in SRAM
    
    Returns:
        Dict with 'text', 'data', 'rodata' as patched bytearray, 'bss_size' as int
    """
    elf = ELFFile(open(elf_path, 'rb'))
    
    # 1. Extract section data
    text_data = bytearray(get_section_data(elf, '.text'))
    text_load_addr = buffer_addresses['text']
    
    # 2. Build symbol table
    symtab = elf.get_section_by_name('.symtab')
    
    # 3. Process each .rel.text entry
    rel_text = elf.get_section_by_name('.rel.text')
    if rel_text:
        for rel in rel_text.iter_relocations():
            r_offset = rel['r_offset']
            r_type = rel['r_info_type']     # pyelftools extracts this
            sym_idx = rel['r_info_sym']     # pyelftools extracts this
            
            symbol = symtab.get_symbol(sym_idx)
            sym_name = symbol.name
            
            # Resolve symbol address
            if symbol['st_shndx'] != 'SHN_UNDEF':
                # Internal symbol: offset within its section
                sym_addr = buffer_addresses['text'] + symbol['st_value']
            else:
                # External symbol: look up in firmware map file
                if sym_name in mapfile.functions:
                    sym_addr = mapfile.functions[sym_name]['address']
                elif sym_name in mapfile.variables:
                    sym_addr = mapfile.variables[sym_name]['address']
                else:
                    raise SymbolResolutionError(
                        f"Unresolved symbol: '{sym_name}'. "
                        f"Not found in firmware map file."
                    )
            
            # Apply THUMB bit for function symbols
            if symbol['st_info']['type'] == 'STT_FUNC':
                sym_addr |= 1
            
            # Apply relocation based on type
            P = text_load_addr + r_offset  # Address of patch site
            
            if r_type == 2:  # R_ARM_ABS32
                A = struct.unpack_from('<I', text_data, r_offset)[0]  # implicit addend
                val = (sym_addr + A) & 0xFFFFFFFF
                struct.pack_into('<I', text_data, r_offset, val)
                
            elif r_type == 10:  # R_ARM_THM_CALL
                A = get_implicit_addend_thm_branch(text_data, r_offset)
                val = (sym_addr + A) - P
                patch_thm_call_or_jump24(text_data, r_offset, val)
                
            elif r_type == 30:  # R_ARM_THM_JUMP24
                A = get_implicit_addend_thm_branch(text_data, r_offset)
                val = (sym_addr + A) - P
                patch_thm_call_or_jump24(text_data, r_offset, val)
                
            elif r_type == 47:  # R_ARM_THM_MOVW_ABS_NC
                A = get_implicit_addend_thm_movw(text_data, r_offset)
                val = (sym_addr + A) & 0xFFFF
                patch_thm_movw(text_data, r_offset, val)
                
            elif r_type == 48:  # R_ARM_THM_MOVT_ABS
                A = get_implicit_addend_thm_movt(text_data, r_offset)
                val = ((sym_addr + A) >> 16) & 0xFFFF
                patch_thm_movt(text_data, r_offset, val)
                
            else:
                raise UnsupportedRelocationError(
                    f"Unsupported relocation type {r_type} for symbol '{sym_name}'"
                )
    
    return {
        'text': bytes(text_data),
        'data': get_section_data(elf, '.data'),
        'rodata': get_section_data(elf, '.rodata'),
        'bss_size': get_section_size(elf, '.bss'),
    }
```

## Specific Corrections Needed in 2026-03-30 Design Document

### Section 3.1 - Relocation Table Format

**Replace entirely.** Current text incorrectly references R_ARM_RELATIVE, 3-field entries, and explicit addend.

Correct content:
- ARM 32-bit ELF uses `.rel.text` (REL format, NOT RELA)
- Each entry is 8 bytes: `r_offset` (4) + `r_info` (4)
- No explicit addend; addend is implicit (read from patch location)
- `r_info` encoding: `type = r_info & 0xFF`, `sym_index = r_info >> 8`
- Supported types: R_ARM_ABS32 (2), R_ARM_THM_CALL (10), R_ARM_THM_JUMP24 (30)
- Possibly also: R_ARM_THM_MOVW_ABS_NC (47), R_ARM_THM_MOVT_ABS (48)

### Section 3.2 - Resolution Algorithm

**Replace entirely.** Current code uses `rel['addend']` (doesn't exist) and `struct.pack_into` for all types.

Correct content:
- Must extract implicit addend from instruction bytes before patching
- R_ARM_ABS32: simple 32-bit write, `val = (S + A) | T`
- R_ARM_THM_CALL/THM_JUMP24: complex Thumb-2 BL encoding with S:I1:I2:imm10:imm11 bits
- Must handle internal vs external symbol resolution separately
- Must know section load addresses for PC-relative calculations

### Section 4.2 - Memory Placement

**Fix addresses.** Change from Flash (0x08000000) to SRAM (0x2000xxxx).
Reference `DYNLD_BUFFER_ADDRESSES` from keyboard model config.

### Section 6.1 - Firmware Handler

**Fix endianness.** Change `(msg[1] << 8) | msg[2]` to `msg[1] | (msg[2] << 8)`.

### Missing: Internal Relocation Handling

**Add section.** Must describe how internal symbols (same compilation unit) are resolved
using ELF symbol table `st_value` + section load address.

### Missing: Reference to 2026-03-29 Plans

**Add references.** The 2026-03-29 designs define the MEL blob format, firmware buffer
layout, and `ElfLoader` class interface that this design should build upon.

## Recommended Approach

Fix the 2026-03-30 design document with all corrections listed above, incorporating the
correct ARM ELF relocation format, proper Thumb-2 encoding/patching logic from LLVM lld,
SRAM memory addresses from the 2026-03-29 design, and the complete resolution algorithm
with internal symbol support. Then proceed to create the implementation plan using the
writing-plans skill.

## Implementation Guidance

- **Objectives**: Correct all 6 identified technical errors in design doc, add missing sections
- **Key Tasks**:
  1. Replace Section 3.1 with correct REL format (8-byte entries, no addend field)
  2. Replace Section 3.2 with correct patching logic per relocation type
  3. Fix Section 4.2 memory addresses (SRAM, not Flash)
  4. Fix Section 6.1 endianness
  5. Add internal relocation handling section
  6. Add references to 2026-03-29 plans
- **Dependencies**: None - this is a document correction task
- **Success Criteria**: Design document is technically accurate per ARM AAELF32 spec and LLVM lld reference implementation
