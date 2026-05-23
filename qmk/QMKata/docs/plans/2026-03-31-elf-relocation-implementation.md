# ELF Relocation Processing - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Python-side ELF relocation processing so dynamically loaded C functions no longer require manual symbol address hardcoding.

**Architecture:** Parse ARM ELF object files with pyelftools, merge per-function sections into a flat blob, resolve all relocations (external via firmware mapfile, internal via ELF symtab), patch the binary in-memory, and send via existing `keyb_set_dynld_function()` protocol. Zero firmware changes for Phase 1.

**Tech Stack:** Python 3, pyelftools 0.32, arm-none-eabi-gcc 13.2, pytest 9.0

**Design doc:** `docs/plans/2026-03-30-elf-relocation-design.md`

---

## Background

### Current Flow
```
C source -> gcc -c -> .o file (named .elf) -> objcopy -O binary -> flat blob -> sysex -> keyboard SRAM
```
**Limitations:** No relocation support. User must manually look up symbol addresses from map file and hardcode them as integer constants in C source (see `kb_scripts/kb_exec_fun.py`).

### New Flow
```
C source -> gcc -c -> .o file -> ElfRelocator.process() -> patched flat blob -> sysex -> keyboard SRAM
```
**Benefits:** Automatic symbol resolution. User writes normal C code with `extern` declarations. The relocator patches all addresses before sending to keyboard.

### Key Technical Facts (verified against ARM AAELF32 spec + LLVM lld)

- ARM 32-bit ELF uses **REL** format (8-byte entries, no explicit addend)
- Without `-fPIC`, only three relocation types appear in practice:
  - `R_ARM_ABS32` (2): 32-bit absolute address in literal pool
  - `R_ARM_THM_CALL` (10): Thumb BL instruction (function call)
  - `R_ARM_THM_JUMP24` (30): Thumb B.W instruction (tail call)
- With `-ffunction-sections`, each function gets its own `.text.funcname` section
- Relocation sections are per-code-section: `.rel.text.funcname`
- Section symbols (STT_SECTION) reference sections like `.data.counter` or `.rodata.msg`
- The firmware buffer address (`dynld_func_buf`) is read from the mapfile
- All code executes from SRAM (0x2000xxxx), not Flash

---

## Task 1: Test Infrastructure and Remove -fPIC

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `keyboards/KeychronQ3Max.py:30`

### Step 1: Create test directory and conftest

Create `tests/__init__.py` (empty) and `tests/conftest.py`:

```python
import pytest
import subprocess
import shutil

ARM_GCC = shutil.which("arm-none-eabi-gcc")

requires_arm_gcc = pytest.mark.skipif(
    ARM_GCC is None,
    reason="arm-none-eabi-gcc not found"
)

COMPILE_FLAGS = [
    "-c", "-mcpu=cortex-m4", "-mthumb",
    "-ffunction-sections", "-fdata-sections", "-Os",
]


@pytest.fixture
def compile_arm(tmp_path):
    """Fixture that returns a function to compile C source to an ARM ELF object file."""
    def _compile(c_source, filename="test.c", extra_flags=None):
        c_file = tmp_path / filename
        c_file.write_text(c_source)
        obj_file = tmp_path / filename.replace(".c", ".o")
        flags = COMPILE_FLAGS + (extra_flags or [])
        subprocess.run(
            [ARM_GCC] + flags + ["-o", str(obj_file), str(c_file)],
            check=True, capture_output=True,
        )
        return str(obj_file)
    return _compile
```

### Step 2: Remove -fPIC from compiler options

In `keyboards/KeychronQ3Max.py:30`, remove `"-fPIC"` from the options list.

Before:
```python
'options': [ "-c", ..., "-fcommon", "-fPIC" ],
```

After:
```python
'options': [ "-c", ..., "-fcommon" ],
```

### Step 3: Verify tests can run

Run: `pytest tests/ -v --co`
Expected: collected 0 items (no tests yet, but no import errors)

### Step 4: Commit

```
git add tests/ keyboards/KeychronQ3Max.py
git commit -m "setup test infrastructure and remove -fPIC from compiler flags"
```

---

## Task 2: Thumb-2 Instruction Helpers

**Files:**
- Create: `ElfRelocator.py`
- Create: `tests/test_elf_relocator.py`

These are low-level byte manipulation functions for encoding/decoding ARM Thumb-2 instructions. They are the foundation for relocation patching.

### Step 1: Write failing tests for basic helpers

Create `tests/test_elf_relocator.py`:

```python
import struct
import pytest
from ElfRelocator import _sign_extend, _read16, _write16


class TestBasicHelpers:
    def test_sign_extend_positive(self):
        assert _sign_extend(0x100, 12) == 0x100

    def test_sign_extend_negative(self):
        assert _sign_extend(0x800, 12) == -2048

    def test_sign_extend_max_positive(self):
        assert _sign_extend(0x7FF, 12) == 0x7FF

    def test_read16_little_endian(self):
        data = bytearray(b'\x34\x12\x78\x56')
        assert _read16(data, 0) == 0x1234
        assert _read16(data, 2) == 0x5678

    def test_write16_little_endian(self):
        data = bytearray(4)
        _write16(data, 0, 0x1234)
        _write16(data, 2, 0x5678)
        assert data == bytearray(b'\x34\x12\x78\x56')
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_elf_relocator.py::TestBasicHelpers -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ElfRelocator'`

### Step 3: Implement basic helpers

Create `ElfRelocator.py`:

```python
"""
ARM ELF relocation processor for dynamically loaded functions.

Parses ARM ELF relocatable object files (.o), resolves relocations using
firmware map file symbols, and produces patched flat binary blobs for
loading to keyboard SRAM.

References:
- ARM AAELF32 spec (2025Q4)
- LLVM lld ARM.cpp
- Design: docs/plans/2026-03-30-elf-relocation-design.md
"""

import struct
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import SH_FLAGS


class SymbolResolutionError(Exception):
    """Raised when a symbol cannot be resolved from mapfile or ELF symtab."""
    pass


class UnsupportedRelocationError(Exception):
    """Raised for relocation types we don't handle."""
    pass


class BufferOverflowError(Exception):
    """Raised when section data exceeds firmware buffer size."""
    pass


# --- Low-level helpers ---

def _sign_extend(val, bits):
    """Sign-extend an unsigned value to a signed integer."""
    if val & (1 << (bits - 1)):
        val -= (1 << bits)
    return val


def _read16(data, offset):
    """Read a 16-bit little-endian value from data at offset."""
    return struct.unpack_from('<H', data, offset)[0]


def _write16(data, offset, val):
    """Write a 16-bit little-endian value to data at offset."""
    struct.pack_into('<H', data, offset, val & 0xFFFF)
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_elf_relocator.py::TestBasicHelpers -v`
Expected: all PASS

### Step 5: Write failing tests for BL/B.W instruction helpers

Add to `tests/test_elf_relocator.py`:

```python
from ElfRelocator import _get_addend_thm_branch, _patch_thm_branch


class TestThumbBranchHelpers:
    def test_roundtrip_forward_offset(self):
        """Patch a forward offset, then extract it back."""
        data = bytearray(b'\x00\xf0\x00\xd0')  # placeholder BL
        offset = 0x1000  # +4096
        _patch_thm_branch(data, 0, offset)
        extracted = _get_addend_thm_branch(data, 0)
        assert extracted == offset

    def test_roundtrip_backward_offset(self):
        """Patch a backward offset, then extract it back."""
        data = bytearray(b'\x00\xf0\x00\xd0')
        offset = -0x1000  # -4096
        _patch_thm_branch(data, 0, offset)
        extracted = _get_addend_thm_branch(data, 0)
        assert extracted == offset

    def test_roundtrip_small_forward(self):
        data = bytearray(b'\x00\xf0\x00\xd0')
        offset = 4
        _patch_thm_branch(data, 0, offset)
        extracted = _get_addend_thm_branch(data, 0)
        assert extracted == offset

    def test_roundtrip_max_range(self):
        """Test near maximum range (+-16 MiB)."""
        data = bytearray(b'\x00\xf0\x00\xd0')
        offset = (1 << 24) - 2  # near max positive, must be even
        _patch_thm_branch(data, 0, offset)
        extracted = _get_addend_thm_branch(data, 0)
        assert extracted == offset

    def test_preserves_bl_opcode(self):
        """Patching should preserve BL vs B.W opcode bits."""
        data_bl = bytearray(b'\x00\xf0\x00\xd0')
        _patch_thm_branch(data_bl, 0, 0x100)
        assert _read16(data_bl, 2) & 0xD000 == 0xD000

    def test_out_of_range_raises(self):
        data = bytearray(b'\x00\xf0\x00\xd0')
        with pytest.raises(AssertionError):
            _patch_thm_branch(data, 0, 1 << 25)  # way out of range
```

### Step 6: Run tests to verify they fail

Run: `pytest tests/test_elf_relocator.py::TestThumbBranchHelpers -v`
Expected: FAIL with `ImportError`

### Step 7: Implement BL/B.W helpers

Add to `ElfRelocator.py`:

```python
def _get_addend_thm_branch(data, offset):
    """Extract implicit addend from Thumb-2 BL/B.W instruction.

    Encoding: S:I1:I2:imm10:imm11:0 (25-bit signed, halfword-aligned)
    Where I1 = NOT(J1 XOR S), I2 = NOT(J2 XOR S)

    Reference: ARM AAELF32 spec, LLVM lld ARM.cpp getImplicitAddend()
    """
    hi = _read16(data, offset)
    lo = _read16(data, offset + 2)

    s = (hi >> 10) & 1
    j1 = (lo >> 13) & 1
    j2 = (lo >> 11) & 1
    i1 = (~(j1 ^ s)) & 1
    i2 = (~(j2 ^ s)) & 1
    imm10 = hi & 0x3FF
    imm11 = lo & 0x7FF

    raw = (s << 24) | (i1 << 23) | (i2 << 22) | (imm10 << 12) | (imm11 << 1)
    return _sign_extend(raw, 25)


def _patch_thm_branch(data, offset, val):
    """Patch Thumb-2 BL/B.W instruction with new PC-relative offset.

    Reference: LLVM lld ARM.cpp relocate() for R_ARM_THM_CALL/R_ARM_THM_JUMP24
    """
    assert -(1 << 24) <= val < (1 << 24), f"Branch offset out of +-16MiB range: {val}"

    lo = _read16(data, offset + 2)

    s = (val >> 24) & 1
    i1 = (val >> 23) & 1
    i2 = (val >> 22) & 1
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    imm10 = (val >> 12) & 0x3FF
    imm11 = (val >> 1) & 0x7FF

    hi = 0xF000 | (s << 10) | imm10
    lo = (lo & 0xD000) | (j1 << 13) | (j2 << 11) | imm11

    _write16(data, offset, hi)
    _write16(data, offset + 2, lo)
```

### Step 8: Run tests to verify they pass

Run: `pytest tests/test_elf_relocator.py::TestThumbBranchHelpers -v`
Expected: all PASS

### Step 9: Commit

```
git add ElfRelocator.py tests/test_elf_relocator.py
git commit -m "add ElfRelocator with Thumb-2 BL/B.W instruction helpers"
```

---

## Task 3: Section Extraction and Merging

**Files:**
- Modify: `ElfRelocator.py`
- Modify: `tests/test_elf_relocator.py`

With `-ffunction-sections -fdata-sections`, the compiler produces per-function/per-variable sections. We need to merge these into a flat blob with tracked offsets.

### Step 1: Write failing tests for section extraction

Add to `tests/test_elf_relocator.py`:

```python
from tests.conftest import requires_arm_gcc
from ElfRelocator import ElfRelocator


@requires_arm_gcc
class TestSectionExtraction:
    """Tests using real compiled ARM ELF object files."""

    def test_extract_text_sections(self, compile_arm):
        """Two functions should produce two .text.* sections merged into text blob."""
        obj = compile_arm("""
            int func_a(int x) { return x + 1; }
            int func_b(int y) { return y * 2; }
        """)
        relocator = ElfRelocator(obj)
        result = relocator.extract_sections()
        assert result['text_size'] > 0
        assert len(result['blob']) >= result['text_size']

    def test_extract_rodata(self, compile_arm):
        """Function with string literal should have rodata."""
        obj = compile_arm("""
            static const char msg[] = "hello world";
            const char* get_msg(void) { return msg; }
        """)
        relocator = ElfRelocator(obj)
        result = relocator.extract_sections()
        assert result['rodata_size'] > 0
        blob = result['blob']
        rodata_start = result['rodata_offset']
        rodata_end = rodata_start + result['rodata_size']
        assert b"hello world" in blob[rodata_start:rodata_end]

    def test_extract_data(self, compile_arm):
        """Static initialized variable should produce .data section."""
        obj = compile_arm("""
            static int counter = 42;
            int get_counter(void) { return counter; }
        """)
        relocator = ElfRelocator(obj)
        result = relocator.extract_sections()
        assert result['data_size'] >= 4

    def test_extract_bss(self, compile_arm):
        """Static uninitialized variable should produce .bss section."""
        obj = compile_arm("""
            static int counter;
            void inc(void) { counter++; }
        """)
        relocator = ElfRelocator(obj)
        result = relocator.extract_sections()
        assert result['bss_size'] >= 4

    def test_blob_layout_order(self, compile_arm):
        """Blob layout: text, rodata, data, bss (in order, no overlap)."""
        obj = compile_arm("""
            static const char msg[] = "test";
            static int val = 7;
            extern int printf(const char *fmt, ...);
            int func(void) { printf(msg); return val; }
        """)
        relocator = ElfRelocator(obj)
        result = relocator.extract_sections()
        assert result['text_offset'] == 0
        assert result['rodata_offset'] >= result['text_size']
        if result['data_size'] > 0:
            assert result['data_offset'] >= result['rodata_offset'] + result['rodata_size']

    def test_section_index_map(self, compile_arm):
        """Section index map should map ELF section indices to blob offsets."""
        obj = compile_arm("""
            int func(int x) { return x; }
        """)
        relocator = ElfRelocator(obj)
        result = relocator.extract_sections()
        assert isinstance(result['section_map'], dict)
        assert len(result['section_map']) > 0
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_elf_relocator.py::TestSectionExtraction -v`
Expected: FAIL with `AttributeError`

### Step 3: Implement ElfRelocator class with section extraction

Add to `ElfRelocator.py`:

```python
# Section type classification
_TEXT_PREFIXES = ('.text',)
_RODATA_PREFIXES = ('.rodata',)
_DATA_PREFIXES = ('.data',)
_BSS_PREFIXES = ('.bss',)


def _align_up(val, alignment):
    """Round val up to the next multiple of alignment."""
    if alignment <= 1:
        return val
    return (val + alignment - 1) & ~(alignment - 1)


def _classify_section(name):
    """Classify a section name into text/rodata/data/bss or None."""
    for prefix in _TEXT_PREFIXES:
        if name == prefix or name.startswith(prefix + '.'):
            return 'text'
    for prefix in _RODATA_PREFIXES:
        if name == prefix or name.startswith(prefix + '.'):
            return 'rodata'
    for prefix in _DATA_PREFIXES:
        if name == prefix or name.startswith(prefix + '.'):
            return 'data'
    for prefix in _BSS_PREFIXES:
        if name == prefix or name.startswith(prefix + '.'):
            return 'bss'
    return None


class ElfRelocator:
    """Processes ARM ELF relocatable object files, resolving relocations.

    Usage:
        relocator = ElfRelocator(elf_path, mapfile=mapfile, load_address=0x20010000)
        result = relocator.process()
        patched_blob = result['blob']
    """

    def __init__(self, elf_path, mapfile=None, load_address=0x20000000):
        self.elf_path = elf_path
        self.mapfile = mapfile
        self.load_address = load_address
        self._elf_file = open(elf_path, 'rb')
        self.elf = ELFFile(self._elf_file)

    def extract_sections(self):
        """Collect all allocatable sections, merge by type into a flat blob.

        Returns dict with:
            blob: bytearray - merged section data
            text_offset, text_size: position of text in blob
            rodata_offset, rodata_size: position of rodata in blob
            data_offset, data_size: position of data in blob
            bss_size: size of bss (not in blob, zero-initialized on firmware)
            section_map: dict of elf_section_index -> offset_in_blob
        """
        groups = {'text': [], 'rodata': [], 'data': [], 'bss': []}

        for i, section in enumerate(self.elf.iter_sections()):
            flags = section['sh_flags']
            if not (flags & SH_FLAGS.SHF_ALLOC):
                continue
            stype = _classify_section(section.name)
            if stype is None:
                continue
            size = section['sh_size']
            if size == 0:
                continue
            groups[stype].append({
                'index': i,
                'name': section.name,
                'data': section.data() if stype != 'bss' else b'',
                'size': size,
                'align': max(section['sh_addralign'], 1),
            })

        blob = bytearray()
        section_map = {}

        def append_group(group_name):
            group_offset = _align_up(len(blob), 4)
            blob.extend(b'\x00' * (group_offset - len(blob)))
            group_start = len(blob)
            for sec in groups[group_name]:
                aligned_pos = _align_up(len(blob), sec['align'])
                blob.extend(b'\x00' * (aligned_pos - len(blob)))
                section_map[sec['index']] = len(blob)
                if group_name != 'bss':
                    blob.extend(sec['data'])
            group_size = len(blob) - group_start
            return group_start, group_size

        text_offset, text_size = append_group('text')
        rodata_offset, rodata_size = append_group('rodata')
        data_offset, data_size = append_group('data')

        bss_size = sum(sec['size'] for sec in groups['bss'])
        bss_pos = _align_up(len(blob), 4)
        for sec in groups['bss']:
            aligned_pos = _align_up(bss_pos, sec['align'])
            section_map[sec['index']] = aligned_pos
            bss_pos = aligned_pos + sec['size']

        return {
            'blob': blob,
            'text_offset': text_offset,
            'text_size': text_size,
            'rodata_offset': rodata_offset,
            'rodata_size': rodata_size,
            'data_offset': data_offset,
            'data_size': data_size,
            'bss_size': bss_size,
            'section_map': section_map,
        }
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_elf_relocator.py::TestSectionExtraction -v`
Expected: all PASS

### Step 5: Commit

```
git add ElfRelocator.py tests/test_elf_relocator.py
git commit -m "add section extraction and merging to ElfRelocator"
```

---

## Task 4: Symbol Resolution and Relocation Processing

**Files:**
- Modify: `ElfRelocator.py`
- Modify: `tests/test_elf_relocator.py`

### Step 1: Write failing tests for symbol resolution

Add to `tests/test_elf_relocator.py`:

```python
from ElfRelocator import SymbolResolutionError


class MockMapfile:
    """Minimal mock of GccMapfile for testing."""
    def __init__(self, functions=None, variables=None):
        self.functions = functions or {}
        self.variables = variables or {}


@requires_arm_gcc
class TestSymbolResolution:

    def test_external_function_resolved(self, compile_arm):
        """External function (printf) should be resolved from mapfile."""
        obj = compile_arm("""
            extern int printf(const char *fmt, ...);
            int func(void) { return printf("hi"); }
        """)
        mapfile = MockMapfile(functions={
            'printf': {'address': 0x08001234, 'size': 100},
        })
        relocator = ElfRelocator(obj, mapfile=mapfile, load_address=0x20010000)
        result = relocator.process()
        assert result['blob'] is not None

    def test_external_variable_resolved(self, compile_arm):
        """External variable should be resolved from mapfile variables."""
        obj = compile_arm("""
            extern int some_global;
            int func(void) { return some_global; }
        """)
        mapfile = MockMapfile(variables={
            'some_global': {'address': 0x20000100, 'size': 4},
        })
        relocator = ElfRelocator(obj, mapfile=mapfile, load_address=0x20010000)
        result = relocator.process()
        assert result['blob'] is not None

    def test_unresolved_symbol_raises(self, compile_arm):
        """Unresolved external symbol should raise SymbolResolutionError."""
        obj = compile_arm("""
            extern int printf(const char *fmt, ...);
            int func(void) { return printf("hi"); }
        """)
        mapfile = MockMapfile()  # empty
        relocator = ElfRelocator(obj, mapfile=mapfile, load_address=0x20010000)
        with pytest.raises(SymbolResolutionError, match="printf"):
            relocator.process()

    def test_internal_function_resolved(self, compile_arm):
        """Internal function call should be resolved from ELF symtab."""
        obj = compile_arm("""
            int helper(int x) { return x * 2; }
            int func(int a) { return helper(a); }
        """)
        relocator = ElfRelocator(obj, load_address=0x20010000)
        result = relocator.process()
        assert result['blob'] is not None

    def test_no_mapfile_external_raises(self, compile_arm):
        """External symbol with no mapfile should raise."""
        obj = compile_arm("""
            extern int printf(const char *fmt, ...);
            int func(void) { return printf("hi"); }
        """)
        relocator = ElfRelocator(obj, load_address=0x20010000)
        with pytest.raises(SymbolResolutionError):
            relocator.process()
```

### Step 2: Run tests to verify they fail

Run: `pytest tests/test_elf_relocator.py::TestSymbolResolution -v`
Expected: FAIL with `AttributeError: 'ElfRelocator' has no attribute 'process'`

### Step 3: Implement symbol resolution and process()

Add to `ElfRelocator` class in `ElfRelocator.py`:

```python
    # ARM relocation type constants (ARM AAELF32 spec)
    R_ARM_ABS32 = 2
    R_ARM_THM_CALL = 10
    R_ARM_THM_JUMP24 = 30

    def _resolve_symbol(self, symbol, sym_name, section_map):
        """Resolve a symbol to its absolute SRAM address.

        Returns (address, is_function) tuple.
        """
        st_shndx = symbol['st_shndx']
        sym_type = symbol['st_info']['type']

        if st_shndx == 'SHN_UNDEF':
            # External symbol: look up in firmware mapfile
            return self._resolve_external(sym_name), sym_type == 'STT_FUNC'
        else:
            # Internal symbol: resolve from ELF symtab + section layout
            sec_idx = st_shndx
            if sec_idx not in section_map:
                raise SymbolResolutionError(
                    f"Symbol '{sym_name}' references section index {sec_idx} "
                    f"which is not in the merged layout"
                )
            sec_base = self.load_address + section_map[sec_idx]

            if sym_type == 'STT_SECTION':
                return sec_base, False
            elif sym_type == 'STT_FUNC':
                # st_value includes Thumb bit for Thumb functions
                clean_offset = symbol['st_value'] & ~1
                return sec_base + clean_offset, True
            else:
                return sec_base + symbol['st_value'], False

    def _resolve_external(self, sym_name):
        """Look up external symbol in firmware mapfile. Fail-fast if not found."""
        if self.mapfile is None:
            raise SymbolResolutionError(
                f"Unresolved external symbol: '{sym_name}'. No mapfile provided."
            )
        if sym_name in self.mapfile.functions:
            return self.mapfile.functions[sym_name]['address']
        if sym_name in self.mapfile.variables:
            return self.mapfile.variables[sym_name]['address']
        raise SymbolResolutionError(
            f"Unresolved external symbol: '{sym_name}'. "
            f"Not found in firmware map file."
        )

    def _process_relocations(self, blob, section_map):
        """Process all .rel.* sections, patching the blob in-place."""
        symtab = self.elf.get_section_by_name('.symtab')
        if symtab is None:
            return

        for section in self.elf.iter_sections():
            if section['sh_type'] != 'SHT_REL':
                continue
            # .rel.text.funcname applies to .text.funcname (sh_info = target index)
            target_idx = section['sh_info']
            if target_idx not in section_map:
                continue

            target_blob_offset = section_map[target_idx]

            for rel in section.iter_relocations():
                r_offset = rel['r_offset']
                r_type = rel['r_info_type']
                sym_idx = rel['r_info_sym']

                symbol = symtab.get_symbol(sym_idx)
                sym_name = symbol.name

                sym_addr, is_func = self._resolve_symbol(
                    symbol, sym_name, section_map
                )

                thumb_bit = 1 if is_func else 0
                patch_off = target_blob_offset + r_offset
                P = self.load_address + patch_off

                if r_type == self.R_ARM_ABS32:
                    A = struct.unpack_from('<I', blob, patch_off)[0]
                    val = ((sym_addr + A) | thumb_bit) & 0xFFFFFFFF
                    struct.pack_into('<I', blob, patch_off, val)

                elif r_type in (self.R_ARM_THM_CALL, self.R_ARM_THM_JUMP24):
                    A = _get_addend_thm_branch(blob, patch_off)
                    val = ((sym_addr + A) | thumb_bit) - P
                    _patch_thm_branch(blob, patch_off, val)

                else:
                    raise UnsupportedRelocationError(
                        f"Unsupported relocation type {r_type} "
                        f"for symbol '{sym_name}' at offset {r_offset:#x}"
                    )

    def process(self):
        """Parse ELF, extract sections, resolve relocations, return patched blob.

        Returns dict with:
            blob: bytes - patched flat binary
            text_size, rodata_size, data_size, bss_size: section sizes
        """
        sections = self.extract_sections()
        blob = sections['blob']
        section_map = sections['section_map']

        self._process_relocations(blob, section_map)

        sections['blob'] = bytes(blob)
        return sections
```

### Step 4: Run tests to verify they pass

Run: `pytest tests/test_elf_relocator.py::TestSymbolResolution -v`
Expected: all PASS

### Step 5: Commit

```
git add ElfRelocator.py tests/test_elf_relocator.py
git commit -m "add symbol resolution and relocation processing to ElfRelocator"
```

---

## Task 5: Relocation Correctness Tests

**Files:**
- Modify: `tests/test_elf_relocator.py`

Verify that patched bytes contain correct addresses.

### Step 1: Write tests that verify patched binary contents

Add to `tests/test_elf_relocator.py`:

```python
@requires_arm_gcc
class TestRelocationCorrectness:
    """Verify that relocations produce correct addresses in the patched blob."""

    def test_abs32_contains_external_address(self, compile_arm):
        """ABS32 relocation should patch literal pool with resolved address."""
        obj = compile_arm("""
            extern int printf(const char *fmt, ...);
            int func(void) { return printf("hi"); }
        """)
        PRINTF_ADDR = 0x08001234
        mapfile = MockMapfile(functions={
            'printf': {'address': PRINTF_ADDR, 'size': 100},
        })
        relocator = ElfRelocator(obj, mapfile=mapfile, load_address=0x20010000)
        result = relocator.process()
        blob = result['blob']

        # printf address with Thumb bit should appear in literal pool
        expected = struct.pack('<I', PRINTF_ADDR | 1)
        assert expected in blob, (
            f"Expected address {PRINTF_ADDR | 1:#010x} not found in blob"
        )

    def test_internal_call_is_pc_relative(self, compile_arm):
        """Internal function call via BL should have correct PC-relative offset."""
        obj = compile_arm("""
            int helper(int x) { return x * 2; }
            int func(int a) { return helper(a) + 1; }
        """)
        relocator = ElfRelocator(obj, load_address=0x20010000)
        result = relocator.process()
        assert len(result['blob']) > 0

    def test_mutual_function_calls(self, compile_arm):
        """Two functions calling each other should both resolve correctly."""
        obj = compile_arm("""
            int func_b(int y);
            int func_a(int x) { return func_b(x + 1); }
            int func_b(int y) { return y > 10 ? y : func_a(y); }
        """)
        relocator = ElfRelocator(obj, load_address=0x20010000)
        result = relocator.process()
        assert len(result['blob']) > 0

    def test_data_section_reference(self, compile_arm):
        """Reference to .data section variable should be patched to SRAM address."""
        obj = compile_arm("""
            static int counter = 42;
            int get(void) { return counter; }
        """)
        LOAD_ADDR = 0x20010000
        relocator = ElfRelocator(obj, load_address=LOAD_ADDR)
        result = relocator.process()
        blob = result['blob']

        # Data section should contain 42
        data_start = result['data_offset']
        data_val = struct.unpack_from('<I', blob, data_start)[0]
        assert data_val == 42

        # Literal pool should reference the data SRAM address
        data_addr = LOAD_ADDR + data_start
        expected = struct.pack('<I', data_addr)
        text_end = result['text_offset'] + result['text_size']
        assert expected in blob[:text_end], (
            f"Expected data address {data_addr:#010x} not found in text section"
        )

    def test_rodata_string_reference(self, compile_arm):
        """Reference to .rodata string should be patched to SRAM address."""
        obj = compile_arm("""
            extern int puts(const char *s);
            static const char msg[] = "test_string_123";
            int func(void) { return puts(msg); }
        """)
        LOAD_ADDR = 0x20010000
        mapfile = MockMapfile(functions={
            'puts': {'address': 0x08002000, 'size': 50},
        })
        relocator = ElfRelocator(obj, mapfile=mapfile, load_address=LOAD_ADDR)
        result = relocator.process()
        blob = result['blob']

        # String should be in rodata
        ro_start = result['rodata_offset']
        ro_end = ro_start + result['rodata_size']
        assert b"test_string_123" in blob[ro_start:ro_end]

        # Rodata address should appear in text literal pool
        rodata_addr = LOAD_ADDR + ro_start
        expected = struct.pack('<I', rodata_addr)
        text_end = result['text_offset'] + result['text_size']
        assert expected in blob[:text_end], (
            f"Expected rodata address {rodata_addr:#010x} not found in text section"
        )
```

### Step 2: Run tests

Run: `pytest tests/test_elf_relocator.py::TestRelocationCorrectness -v`
Expected: all PASS (if not, debug and fix)

### Step 3: Commit

```
git add tests/test_elf_relocator.py
git commit -m "add relocation correctness tests for ElfRelocator"
```

---

## Task 6: Integration with KeybScriptEnv

**Files:**
- Modify: `QMKataKeyboard.py:344-380` (KeybScriptEnv.compile, load_fun, exec)
- Modify: `keyboards/KeychronQ3Max.py` (add DYNLD_BUFFER config)

### Step 1: Add buffer address config to KeychronQ3Max

Add after `TOOLCHAIN` dict in `keyboards/KeychronQ3Max.py`:

```python
    # SRAM buffer address for dynamically loaded functions
    # Read from firmware mapfile variable 'dynld_func_buf'
    DYNLD_BUFFER_VARIABLE = 'dynld_func_buf'
```

### Step 2: Update KeybScriptEnv.compile() to use ElfRelocator

Replace the `compile()` method in `QMKataKeyboard.py` (line 344) with:

```python
        def compile(self, c_file):
            if self.toolchain:
                elf_file = c_file.replace(".c", ".elf")
                bin_file = elf_file.replace(".elf", ".bin")
                if self.toolchain.compile(c_file, elf_file):
                    elf_data = None
                    bin_data = None
                    with open(elf_file, "rb") as f:
                        elf_data = f.read()

                    # Try relocation-based loading (new path)
                    if self.mapfile:
                        try:
                            from ElfRelocator import ElfRelocator
                            load_addr = self._get_dynld_buffer_address()
                            relocator = ElfRelocator(
                                elf_file,
                                mapfile=self.mapfile,
                                load_address=load_addr,
                            )
                            result = relocator.process()
                            bin_data = result['blob']
                            self.dbg.tr('D', "ElfRelocator: patched {} bytes, "
                                        "text={} rodata={} data={} bss={}",
                                        len(bin_data),
                                        result['text_size'],
                                        result['rodata_size'],
                                        result['data_size'],
                                        result['bss_size'])
                        except Exception as e:
                            self.dbg.tr('E', "ElfRelocator failed: {}, "
                                        "falling back to objcopy", e)
                            bin_data = None

                    # Fallback: objcopy binary (no relocations)
                    if bin_data is None:
                        if self.toolchain.elf2bin(elf_file, bin_file):
                            with open(bin_file, "rb") as f:
                                bin_data = f.read()

                    return { 'elf': elf_data, 'bin': bin_data }
            return None

        def _get_dynld_buffer_address(self):
            """Get SRAM address of firmware's dynld function buffer."""
            try:
                buf_var = self.keyboard.keyboardModel.DYNLD_BUFFER_VARIABLE
                return self.mapfile.variables[buf_var]['address']
            except (AttributeError, KeyError):
                return 0x20010000
```

### Step 3: Commit

```
git add QMKataKeyboard.py keyboards/KeychronQ3Max.py
git commit -m "integrate ElfRelocator into KeybScriptEnv.compile()"
```

---

## Task 7: Simplify Example Script

**Files:**
- Create: `kb_scripts/kb_exec_fun_v2.py`

### Step 1: Create simplified example that uses automatic relocation

```python
# Example: compile and execute a C function on the keyboard
# With ELF relocation, no manual symbol address lookup needed!
# Compare with kb_exec_fun.py which required manual address hardcoding.

hello_world_c = """
#include <stdint.h>

// These are resolved automatically from the firmware map file
extern int printf(const char* fmt, ...);
extern const char __QMK_BUILDDATE__[];

int hello_world(int a) {
    printf("Build: %s\\n", __QMK_BUILDDATE__);
    printf("Hello from dynamic code! arg=%d\\n", a);
    return 0x5adcbaa5;
}
"""

with open("exec.c", "w") as f:
    f.write(hello_world_c)

code = kb.compile("exec.c")
if not code or not code['bin']:
    print("compile failed")
    exit()

rc = kb.exec(code['bin'])
print(f"rc: {hex(rc)}")
```

### Step 2: Commit

```
git add kb_scripts/kb_exec_fun_v2.py
git commit -m "add simplified example script using automatic symbol resolution"
```

---

## Task 8: End-to-End Validation and Cleanup

**Files:**
- Modify: `tests/test_elf_relocator.py`

### Step 1: Add comprehensive integration test

```python
@requires_arm_gcc
class TestEndToEnd:
    """Full pipeline tests simulating real usage."""

    def test_hello_world_like_kb_exec_fun(self, compile_arm):
        """Simulate the kb_exec_fun.py use case with automatic resolution."""
        obj = compile_arm("""
            extern int printf(const char* fmt, ...);
            extern const char __QMK_BUILDDATE__[];

            int hello_world(int a) {
                printf("Build: %s\\n", __QMK_BUILDDATE__);
                printf("Hello! arg=%d\\n", a);
                return 0x5adcbaa5;
            }
        """)
        mapfile = MockMapfile(
            functions={'printf': {'address': 0x08001234, 'size': 100}},
            variables={'__QMK_BUILDDATE__': {'address': 0x08040000, 'size': 20}},
        )
        relocator = ElfRelocator(obj, mapfile=mapfile, load_address=0x20010000)
        result = relocator.process()

        blob = result['blob']
        assert len(blob) > 0
        assert result['text_size'] > 0
        assert result['rodata_size'] > 0

        # Verify resolved addresses appear in the blob
        assert struct.pack('<I', 0x08001234 | 1) in blob  # printf (Thumb)
        assert struct.pack('<I', 0x08040000) in blob       # __QMK_BUILDDATE__

    def test_animation_like_usage(self, compile_arm):
        """Simulate dynld animation: single function, no external calls."""
        obj = compile_arm("""
            typedef struct { unsigned char h, s, v; } HSV;
            HSV effect(int led_index, int time) {
                HSV hsv;
                hsv.h = (led_index + time) & 0xFF;
                hsv.s = 255;
                hsv.v = 200;
                return hsv;
            }
        """)
        relocator = ElfRelocator(obj, load_address=0x20010000)
        result = relocator.process()
        assert len(result['blob']) > 0
        assert result['text_size'] > 0

    def test_empty_function(self, compile_arm):
        """Trivial function with no relocations should work."""
        obj = compile_arm("""
            int noop(void) { return 42; }
        """)
        relocator = ElfRelocator(obj, load_address=0x20010000)
        result = relocator.process()
        assert len(result['blob']) > 0
```

### Step 2: Run all tests

Run: `pytest tests/ -v`
Expected: all PASS

### Step 3: Commit

```
git add tests/test_elf_relocator.py
git commit -m "add end-to-end integration tests for ELF relocation pipeline"
```

---

## Summary

| Task | Files | Estimated Time |
|------|-------|---------------|
| 1. Test infra + remove -fPIC | `tests/conftest.py`, `KeychronQ3Max.py` | 15 min |
| 2. Thumb-2 helpers | `ElfRelocator.py`, `tests/test_elf_relocator.py` | 30 min |
| 3. Section extraction | `ElfRelocator.py`, `tests/test_elf_relocator.py` | 30 min |
| 4. Symbol resolution | `ElfRelocator.py`, `tests/test_elf_relocator.py` | 30 min |
| 5. Correctness tests | `tests/test_elf_relocator.py` | 20 min |
| 6. Integration | `QMKataKeyboard.py`, `KeychronQ3Max.py` | 20 min |
| 7. Example script | `kb_scripts/kb_exec_fun_v2.py` | 10 min |
| 8. E2E validation | `tests/test_elf_relocator.py` | 15 min |
| **Total** | | **~2.5 hours** |

## Key Design Decisions

1. **Remove `-fPIC`**: Eliminates GOT relocations. Only R_ARM_ABS32, R_ARM_THM_CALL, R_ARM_THM_JUMP24 needed.
2. **Flat blob approach**: Merge all sections into single blob, same as `objcopy -O binary` but with relocations patched. Zero firmware/protocol changes.
3. **Fallback to objcopy**: If ElfRelocator fails (e.g., missing mapfile), fall back to current objcopy approach.
4. **Load address from mapfile**: `dynld_func_buf` variable address from firmware mapfile.
5. **Section merging handles `-ffunction-sections`**: Per-function sections are merged in order with alignment.
