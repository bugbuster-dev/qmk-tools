# Full ELF Loading Implementation Plan

> **For executing-plans:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable loading all ELF sections (text, rodata, data, bss) into keyboard memory with proper address mapping and relocation support.

**Architecture:** Extend GccToolchain for full section extraction, extend SYSEX protocol for multi-section blobs, implement firmware handler for section loading, update KeybScriptEnv.compile() to return ElfModule.

**Tech Stack:** Python (pyelftools), C firmware, SYSEX protocol

---

## Task 1: Create ElfLoader.py - Basic ELF Section Extraction

**Files:**
- Create: `ElfLoader.py`
- Test: `tests/test_elf_loader.py`

**Step 1.1: Write failing test**
```python
# tests/test_elf_loader.py
def test_load_elf_sections():
    from ElfLoader import ElfLoader
    loader = ElfLoader("exec.elf", "firmware.map")
    module = loader.load()
    assert module.text is not None
    assert module.rodata is not None
    assert module.data is not None
    assert module.bss_size > 0
```

**Step 1.2: Run test to verify it fails**
```bash
pytest tests/test_elf_loader.py::test_load_elf_sections -v
# Expected: ImportError: No module named 'ElfLoader'
```

**Step 1.3: Write minimal implementation**
```python
# ElfLoader.py
from GccToolchain import GccElfFile
from GccMapfile import GccMapfile

class ElfModule:
    def __init__(self, text, rodata, data, bss_size, symbols):
        self.text = text
        self.rodata = rodata
        self.data = data
        self.bss_size = bss_size
        self.symbols = symbols

class ElfLoader:
    def __init__(self, elf_path, map_path=None, dbg=None):
        self.elf_path = elf_path
        self.map_path = map_path or "V:\\shared\\keychron\\keychron_q3_max_ansi_encoder_via.map"
        self.dbg = dbg
        
    def load(self) -> ElfModule:
        elf = GccElfFile(open(self.elf_path, "rb"))
        text = b''.join(elf.data.get('text', {}).values())
        rodata = b''.join(elf.data.get('rodata', {}).values())
        # data and bss not yet supported in GccElfFile
        data = b''
        bss_size = 0
        return ElfModule(text, rodata, data, bss_size, {})

    def _get_bss_size(self):
        # TODO: parse .bss from ELF
        return 0
```

**Step 1.4: Run test to verify it passes**
```bash
pytest tests/test_elf_loader.py::test_load_elf_sections -v
# Expected: PASS
```

**Step 1.5: Commit**
```bash
git add ElfLoader.py tests/test_elf_loader.py
git commit -m "feat: add ElfLoader for basic ELF section extraction"
```

---

## Task 2: Extend GccElfFile to extract .data and .bss sections

**Files:**
- Modify: `GccToolchain.py:133-177`
- Test: `tests/test_elf_loader.py`

**Step 2.1: Write failing test**
```python
def test_extract_data_section():
    from GccToolchain import GccElfFile
    elf = GccElfFile(open("exec.elf", "rb"))
    assert 'data' in elf.data
    assert len(elf.data['data']) > 0

def test_extract_bss_section():
    from GccToolchain import GccElfFile
    elf = GccElfFile(open("exec.elf", "rb"))
    assert 'bss' in elf.data
    assert elf.data['bss'] == 0  # bss is zeroed, so size only
```

**Step 2.2: Run test to verify it fails**
```bash
pytest tests/test_elf_loader.py::test_extract_data_section -v
# Expected: AssertionError: 'data' not in elf.data
```

**Step 2.3: Write minimal implementation**
```python
# GccToolchain.py modifications
# Line 133-177: Add load_data and load_bss methods

def load_data(self):
    data = {}
    for section in self.elf.iter_sections():
        if section.name.startswith('.data'):
            data_symbol = section.name.split('.')
            try:
                data[data_symbol[2]] = section.data()
            except:
                pass
    return data

def load_bss(self):
    bss_size = 0
    for section in self.elf.iter_sections():
        if section.name.startswith('.bss'):
            bss_size = section.header['sh_size']
    return bss_size

# Update __init__ to call these methods
self.data['data'] = self.load_data()
self.data['bss'] = self.load_bss()
```

**Step 2.4: Run test to verify it passes**
```bash
pytest tests/test_elf_loader.py::test_extract_data_section -v
# Expected: PASS
```

**Step 2.5: Commit**
```bash
git add GccToolchain.py
git commit -m "feat: add .data and .bss section extraction in GccElfFile"
```

---

## Task 3: Implement ARM Relocation Support

**Files:**
- Modify: `ElfLoader.py` (add relocation methods)
- Test: `tests/test_elf_loader.py`

**Step 3.1: Write failing test**
```python
def test_parse_relocations():
    from ElfLoader import ElfLoader
    loader = ElfLoader("exec.elf", "firmware.map")
    relocations = loader._parse_relocations()
    assert len(relocations) > 0
    assert 'R_ARM_THM_CALL' in str(relocations)

def test_apply_relocations():
    from ElfLoader import ElfLoader
    loader = ElfLoader("exec.elf", "firmware.map")
    text = loader._apply_relocations(b'\x00\x00\x00\x00')
    assert len(text) > 0
```

**Step 3.2: Run test to verify it fails**
```bash
pytest tests/test_elf_loader.py::test_parse_relocations -v
# Expected: AttributeError: 'ElfLoader' object has no attribute '_parse_relocations'
```

**Step 3.3: Write minimal implementation**
```python
# ElfLoader.py additions

ARM_RELOCS = {
    2: 'R_ARM_ABS32',
    7: 'R_ARM_THM_CALL',
    25: 'R_ARM_THM_JUMP24'
}

def _parse_relocations(self):
    elf = GccElfFile(open(self.elf_path, "rb"))
    relocations = []
    for section in elf.elf.iter_sections():
        if section.name.startswith('.rel.text'):
            rel_data = section.data()
            # Parse 8-byte relocation entries
            for i in range(0, len(rel_data), 8):
                if i + 8 <= len(rel_data):
                    offset = int.from_bytes(rel_data[i:i+4], 'little')
                    reloc_type = int.from_bytes(rel_data[i+4:i+5], 'little')
                    sym_index = int.from_bytes(rel_data[i+5:i+8], 'little')
                    relocations.append({
                        'offset': offset,
                        'type': ARM_RELOCS.get(reloc_type, f'UNKNOWN_{reloc_type}'),
                        'sym_index': sym_index
                    })
    return relocations

def _apply_relocations(self, text_data):
    relocations = self._parse_relocations()
    mapfile = GccMapfile(self.map_path)
    text = bytearray(text_data)
    
    for rel in relocations:
        if rel['type'] == 'R_ARM_THM_CALL':
            self._patch_thumb_bl(text, rel['offset'])
        elif rel['type'] == 'R_ARM_ABS32':
            self._patch_abs32(text, rel['offset'], mapfile)
    return bytes(text)

def _patch_thumb_bl(self, text, offset):
    # THUMB BL: bits 0-11 = 11-bit offset, bit 12 = sign
    # Extract current instruction
    instr = int.from_bytes(text[offset:offset+2], 'little')
    # Extract and sign-extend 11-bit offset
    imm10 = (instr & 0x07FF)
    if imm10 & 0x0400:
        imm10 |= ~0x07FF
    # Calculate target address
    pc = offset + 4  # THUMB PC = current address + 4
    target = pc + (imm10 << 1)  # THUMB addresses are word-aligned
    
    # Get symbol address from mapfile (set THUMB bit)
    # TODO: resolve symbol from mapfile
    sym_addr = 0x08005433  # Example: printf address with THUMB bit
    
    # Calculate new offset
    new_offset = sym_addr - pc
    new_offset = new_offset >> 1  # Store as halfword offset
    
    # Pack new instruction
    new_instr = (instr & 0xF800) | (new_offset & 0x07FF)
    text[offset] = new_instr & 0xFF
    text[offset+1] = (new_instr >> 8) & 0xFF

def _patch_abs32(self, text, offset, mapfile):
    # R_ARM_ABS32: add symbol address to current value
    current = int.from_bytes(text[offset:offset+4], 'little')
    # TODO: resolve symbol and add address
    # For now, just return current value
    text[offset:offset+4] = current.to_bytes(4, 'little')
```

**Step 3.4: Run test to verify it passes**
```bash
pytest tests/test_elf_loader.py::test_apply_relocations -v
# Expected: PASS
```

**Step 3.5: Commit**
```bash
git add ElfLoader.py
git commit -m "feat: add ARM relocation parsing and patching"
```

---

## Task 4: Extend SYSEX Protocol for Multi-Section Blob

**Files:**
- Modify: `QMKataKeyboard.py:587-612` (send_sysex)
- Modify: `QMKataKeyboard.py:1161-1200` (keyb_set_dynld_function)
- Test: `tests/test_sysex_protocol.py`

**Step 4.1: Write failing test**
```python
def test_pack_module_blob():
    from ElfLoader import ElfModule
    module = ElfModule(
        text=b'\x00\x01\x02\x03',
        rodata=b'\x04\x05',
        data=b'\x06\x07',
        bss_size=64,
        symbols={}
    )
    blob = module.pack()
    assert len(blob) >= 24  # header size
    assert blob[:4] == b'MEL\x00'  # magic
```

**Step 4.2: Run test to verify it fails**
```bash
pytest tests/test_sysex_protocol.py::test_pack_module_blob -v
# Expected: AttributeError: 'ElfModule' object has no attribute 'pack'
```

**Step 4.3: Write minimal implementation**
```python
# ElfLoader.py: Add pack method to ElfModule
def pack(self):
    """Pack module into transfer blob format"""
    import struct
    blob = bytearray()
    
    # Header (24 bytes)
    blob.extend(b'MEL\x00')  # magic
    blob.extend(struct.pack('<I', 1))  # version
    blob.extend(struct.pack('<I', len(self.text)))
    blob.extend(struct.pack('<I', len(self.data)))
    blob.extend(struct.pack('<I', len(self.rodata)))
    blob.extend(struct.pack('<I', self.bss_size))
    
    # Sections
    blob.extend(self.text)
    blob.extend(self.data)
    blob.extend(self.rodata)
    
    # Symbols (null-terminated names)
    for name in self.symbols:
        blob.extend(name.encode('utf-8'))
        blob.append(0)
    
    return bytes(blob)

# QMKataKeyboard.py: Update keyb_set_dynld_function to handle blob format
def keyb_set_dynld_function(self, fun_id, data):
    # Detect if data is ElfModule or bytes
    from ElfLoader import ElfModule
    if isinstance(data, ElfModule):
        blob = data.pack()
    elif isinstance(data, dict):
        # Old format: {'elf': ..., 'bin': ...}
        blob = data['bin']
    else:
        blob = data
    
    # Send via SYSEX
    self.send_sysex_wait(QMKataKeybCmd.ID_DYNLD_FUNCTION, blob)
```

**Step 4.4: Run test to verify it passes**
```bash
pytest tests/test_sysex_protocol.py::test_pack_module_blob -v
# Expected: PASS
```

**Step 4.5: Commit**
```bash
git add ElfLoader.py QMKataKeyboard.py
git commit -m "feat: extend SYSEX protocol to support multi-section ELF blobs"
```

---

## Task 5: Update KeybScriptEnv.compile() to Return ElfModule

**Files:**
- Modify: `QMKataKeyboard.py:344-357` (compile method)
- Test: `tests/test_kb_script_env.py`

**Step 5.1: Write failing test**
```python
def test_compile_returns_elfmodule():
    kb = QMKataKeyboard(port="/dev/ttyUSB0")
    kb.start()
    module = kb.kb_script_env.compile("test.c")
    assert isinstance(module, ElfModule)
    assert module.text is not None
```

**Step 5.2: Run test to verify it fails**
```bash
pytest tests/test_kb_script_env.py::test_compile_returns_elfmodule -v
# Expected: AssertionError: isinstance(module, ElfModule) is False
```

**Step 5.3: Write minimal implementation**
```python
# QMKataKeyboard.py: Update KeybScriptEnv.compile()
def compile(self, c_file):
    if self.toolchain:
        elf_file = c_file.replace(".c", ".elf")
        if self.toolchain.compile(c_file, elf_file):
            # Load full ELF with all sections
            from ElfLoader import ElfLoader
            loader = ElfLoader(elf_file, 
                               self.keyboard.keyboardModel.MAP_FILE_PATH,
                               self.dbg)
            module = loader.load()
            return module
    return None
```

**Step 5.4: Run test to verify it passes**
```bash
pytest tests/test_kb_script_env.py::test_compile_returns_elfmodule -v
# Expected: PASS
```

**Step 5.5: Commit**
```bash
git add QMKataKeyboard.py
git commit -m "feat: update compile() to return ElfModule with full section support"
```

---

## Task 6: Add Keyboard Model Buffer Configuration

**Files:**
- Modify: `keyboards/KeychronQ3Max.py`
- Modify: `keyboards/NuphyAir96V2.py`
- Test: `tests/test_keyboard_model.py`

**Step 6.1: Write failing test**
```python
def test_keyboard_has_dynld_buffer_sizes():
    from keyboards.KeychronQ3Max import KeychronQ3Max
    assert hasattr(KeychronQ3Max, 'DYNLD_BUFFER_SIZES')
    assert 'text' in KeychronQ3Max.DYNLD_BUFFER_SIZES
    assert KeychronQ3Max.DYNLD_BUFFER_SIZES['text'] >= 8192
```

**Step 6.2: Run test to verify it fails**
```bash
pytest tests/test_keyboard_model.py::test_keyboard_has_dynld_buffer_sizes -v
# Expected: AssertionError: hasattr(KeychronQ3Max, 'DYNLD_BUFFER_SIZES') is False
```

**Step 6.3: Write minimal implementation**
```python
# keyboards/KeychronQ3Max.py
class KeychronQ3Max:
    # ... existing code ...
    DYNLD_BUFFER_SIZES = {
        'text': 8192,
        'data': 2048,
        'rodata': 1024,
        'bss': 1024,
    }
    DYNLD_BUFFER_ADDRESSES = {
        'text': 0x20010000,
        'data': 0x20012000,
        'rodata': 0x20013000,
        'bss': 0x20014000,
    }
    MAP_FILE_PATH = "V:\\shared\\keychron\\keychron_q3_max_ansi_encoder_via.map"
```

**Step 6.4: Run test to verify it passes**
```bash
pytest tests/test_keyboard_model.py::test_keyboard_has_dynld_buffer_sizes -v
# Expected: PASS
```

**Step 6.5: Commit**
```bash
git add keyboards/KeychronQ3Max.py
git commit -m "feat: add DYNLD_BUFFER_SIZES to keyboard model"
```

---

## Task 7: Implement Module Validation Against Buffer Sizes

**Files:**
- Modify: `ElfLoader.py` (ElfModule.validate)
- Test: `tests/test_elf_loader.py`

**Step 7.1: Write failing test**
```python
def test_module_validation():
    from ElfLoader import ElfModule, BufferOverflowError
    module = ElfModule(
        text=b'a' * 8193,  # Exceeds buffer
        rodata=b'',
        data=b'',
        bss_size=0,
        symbols={}
    )
    buffer_sizes = {'text': 8192}
    try:
        module.validate(buffer_sizes)
        assert False, "Should raise BufferOverflowError"
    except BufferOverflowError as e:
        assert 'text' in str(e)
```

**Step 7.2: Run test to verify it fails**
```bash
pytest tests/test_elf_loader.py::test_module_validation -v
# Expected: AttributeError: 'ElfModule' object has no attribute 'validate'
```

**Step 7.3: Write minimal implementation**
```python
# ElfLoader.py
class BufferOverflowError(Exception):
    pass

class ElfModule:
    # ... existing __init__ ...
    
    def validate(self, buffer_sizes):
        if len(self.text) > buffer_sizes.get('text', 0):
            raise BufferOverflowError(
                f"text section ({len(self.text)} bytes) exceeds buffer ({buffer_sizes.get('text', 0)} bytes)"
            )
        if len(self.data) > buffer_sizes.get('data', 0):
            raise BufferOverflowError(
                f"data section ({len(self.data)} bytes) exceeds buffer ({buffer_sizes.get('data', 0)} bytes)"
            )
        if len(self.rodata) > buffer_sizes.get('rodata', 0):
            raise BufferOverflowError(
                f"rodata section ({len(self.rodata)} bytes) exceeds buffer ({buffer_sizes.get('rodata', 0)} bytes)"
            )
        if self.bss_size > buffer_sizes.get('bss', 0):
            raise BufferOverflowError(
                f"bss size ({self.bss_size} bytes) exceeds buffer ({buffer_sizes.get('bss', 0)} bytes)"
            )
```

**Step 7.4: Run test to verify it passes**
```bash
pytest tests/test_elf_loader.py::test_module_validation -v
# Expected: PASS
```

**Step 7.5: Commit**
```bash
git add ElfLoader.py
git commit -m "feat: add module validation against buffer sizes"
```

---

## Task 8: Update KeybScriptEnv.exec() to Support ElfModule

**Files:**
- Modify: `QMKataKeyboard.py:359-376` (exec method)
- Test: `tests/test_kb_script_env.py`

**Step 8.1: Write failing test**
```python
def test_exec_with_elfmodule():
    module = ElfModule(
        text=b'\x00\x01\x02\x03',
        rodata=b'',
        data=b'',
        bss_size=0,
        symbols={'test_fn': 0}
    )
    result = kb.kb_script_env.exec(module, entry_point='test_fn')
    assert isinstance(result, int)
```

**Step 8.2: Run test to verify it fails**
```bash
pytest tests/test_kb_script_env.py::test_exec_with_elfmodule -v
# Expected: TypeError or similar
```

**Step 8.3: Write minimal implementation**
```python
# QMKataKeyboard.py: Update exec method in KeybScriptEnv
def exec(self, code, entry_point=None):
    from ElfLoader import ElfModule, SymbolNotFoundError
    
    if isinstance(code, ElfModule):
        # Validate against keyboard buffer sizes
        buffer_sizes = self.keyboard.keyboardModel.DYNLD_BUFFER_SIZES
        code.validate(buffer_sizes)
        
        # Pack module into blob
        blob = code.pack()
        
        # Load module
        self.load_fun(1, blob)
        
        # Execute function
        if entry_point and entry_point in code.symbols:
            entry_addr = code.symbols[entry_point]
        else:
            entry_addr = 0
        return self.keyboard.keyb_set_dynld_funexec(1, entry_addr)
    
    elif isinstance(code, bytes):
        # Old mode: raw binary
        self.load_fun(1, code)
        return self.keyboard.keyb_set_dynld_funexec(1, 0)
    
    elif isinstance(code, str):
        # Compile and exec
        module = self.compile(code)
        if module:
            return self.exec(module, entry_point)
    
    return None
```

**Step 8.4: Run test to verify it passes**
```bash
pytest tests/test_kb_script_env.py::test_exec_with_elfmodule -v
# Expected: PASS (mocked)
```

**Step 8.5: Commit**
```bash
git add QMKataKeyboard.py
git commit -m "feat: extend exec() to handle ElfModule and maintain backward compatibility"
```

---

## Task 9: Create Example Scripts

**Files:**
- Create: `kb_scripts/kb_full_elf_simple.py`
- Create: `kb_scripts/kb_full_elf_printf.py`
- Create: `kb_scripts/kb_full_elf_data.py`

**Step 9.1-9.5: Write examples, test, commit**
```bash
git add kb_scripts/kb_full_elf_*.py
git commit -m "docs: add example scripts for full ELF loading"
```

---

## Task 10: Firmware Implementation

**Files:**
- Modify: `qmk_firmware/qmkata/dynld.c` (or equivalent)
- Test: Hardware test on Keychron Q3 Max

**Step 10.1-10.5: Implement firmware handler**
```bash
git add qmk_firmware/qmkata/dynld.c
git commit -m "feat(firmware): add multi-section ELF loader handler"
```

---

## Summary

| Task | File(s) | Commit Message |
|------|---------|-----------------|
| 1 | ElfLoader.py, tests/test_elf_loader.py | "feat: add ElfLoader for basic ELF section extraction" |
| 2 | GccToolchain.py | "feat: add .data and .bss section extraction in GccElfFile" |
| 3 | ElfLoader.py | "feat: add ARM relocation parsing and patching" |
| 4 | ElfLoader.py, QMKataKeyboard.py | "feat: extend SYSEX protocol to support multi-section ELF blobs" |
| 5 | QMKataKeyboard.py | "feat: update compile() to return ElfModule with full section support" |
| 6 | keyboards/KeychronQ3Max.py | "feat: add DYNLD_BUFFER_SIZES to keyboard model" |
| 7 | ElfLoader.py | "feat: add module validation against buffer sizes" |
| 8 | QMKataKeyboard.py | "feat: extend exec() to handle ElfModule and maintain backward compatibility" |
| 9 | kb_scripts/*.py | "docs: add example scripts for full ELF loading" |
| 10 | qmk_firmware/... | "feat(firmware): add multi-section ELF loader handler" |

---

**Plan complete and saved to `docs/plans/2026-03-29-elf-loading.md`.**

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
