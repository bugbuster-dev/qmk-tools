# Full ELF Loading Design for QMKata

**Date:** 2026-03-29  
**Author:** QMKata Development  
**Status:** Design Approved - Ready for Implementation

---

## Executive Summary

This design extends QMKata's keyboard scripting to support loading complete ELF modules (with `.text`, `.data`, `.rodata`, and `.bss` sections) into pre-allocated firmware buffers, with automatic symbol resolution and relocation patching at load time.

### Key Features
- **Full ELF support**: Load `.text`, `.data`, `.rodata`, `.bss` sections
- **Automatic relocation**: ELF relocations parsed and patched at load time
- **Firmware symbol resolution**: External symbols resolved from firmware map file
- **Per-keyboard configuration**: Buffer sizes configurable per keyboard model
- **Backward compatible**: `exec()` accepts both raw binary and ElfModule

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Data Formats](#2-data-formats)
3. [Component Design](#3-component-design)
4. [Relocation System](#4-relocation-system)
5. [Execution Flow](#5-execution-flow)
6. [Error Handling](#6-error-handling)
7. [Testing Strategy](#7-testing-strategy)
8. [Firmware Requirements](#8-firmware-requirements)
9. [Migration Path](#9-migration-path)
10. [Risks and Mitigations](#10-risks-and-mitigations)

---

## 1. Architecture

### 1.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      Host (Python)                              │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │  kb_exec_fun.py  │    │  kb_script.py    │                  │
│  │  (user scripts)  │    │  (user scripts)  │                  │
│  └────────┬─────────┘    └────────┬─────────┘                  │
│           │                       │                             │
│           └───────────┬───────────┘                             │
│                       ▼                                         │
│  ┌──────────────────────────────────────────────────────┐     │
│  │           KeybScriptEnv (QMKataKeyboard.py)          │     │
│  │                                                       │     │
│  │  compile() → GccToolchain → ElfLoader               │     │
│  │  exec() → pack_module() → send_sysex()              │     │
│  └───────────────────────┬──────────────────────────────┘     │
│                          │ send_sysex(ID_DYNLD_FUNCTION)       │
└──────────────────────────┼─────────────────────────────────────┘
                           │ USB/Serial
┌──────────────────────────┼─────────────────────────────────────┐
│                     Keyboard Firmware                           │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐     │
│  │            dynld_handler (qmk_firmware)              │     │
│  │                                                       │     │
│  │  receive blob → unpack sections                      │     │
│  │    ├─ copy .text → dynld_text_buf                    │     │
│  │    ├─ copy .data → dynld_data_buf                    │     │
│  │    ├─ copy .rodata → dynld_rodata_buf                │     │
│  │    └─ zero .bss → dynld_bss_buf                      │     │
│  └───────────────────────┬──────────────────────────────┘     │
│                          │                                     │
│  ┌───────────────────────┴──────────────────────────────┐     │
│  │              Pre-allocated Buffers                   │     │
│  │  uint8_t dynld_text_buf[8192];  @0x2000xxx          │     │
│  │  uint8_t dynld_data_buf[2048];  @0x2000yyy          │     │
│  │  uint8_t dynld_rodata_buf[1024]; @0x2000zzz         │     │
│  │  uint8_t dynld_bss_buf[1024];     @0x2000www        │     │
│  └──────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────┘
```

### 1.2 Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Static symbol resolution at load time** | No runtime relocation needed; simpler firmware |
| **Single blob transfer** | Minimal protocol changes; atomic load |
| **Pre-allocated buffers** | No dynamic allocation on MCU; predictable memory usage |
| **Host-side ELF patching** | Leverages Python's pyelftools; firmware stays simple |
| **ARM THUMB mode support** | Cortex-M4 uses THUMB; function pointers need bit-0 set |
| **Per-keyboard buffer config** | Different keyboards have different memory constraints |
| **Backward compatible exec()** | Existing scripts continue to work |

---

## 2. Data Formats

### 2.1 ELF Module Blob Format

```
┌─────────────────────────────────────────────────────────────────┐
│                    MODULE HEADER (24 bytes)                     │
├────────────┬────────────┬────────────┬─────────────────────────┤
│ Offset     │ Size       │ Field      │ Description             │
├────────────┼────────────┼────────────┼─────────────────────────┤
│ 0x00       │ 4          │ magic      │ 0x454C464D ("MEL" + NUL)│
│ 0x04       │ 4          │ version    │ 0x00000001              │
│ 0x08       │ 4          │ text_size  │ .text section size      │
│ 0x0C       │ 4          │ data_size  │ .data section size      │
│ 0x10       │ 4          │ rodata_size│ .rodata section size    │
│ 0x14       │ 4          │ bss_size   │ .bss section size       │
├─────────────────────────────────────────────────────────────────┤
│                    TEXT SECTION (variable)                      │
│                    (relocations already applied)                │
├─────────────────────────────────────────────────────────────────┤
│                    DATA SECTION (variable)                      │
├─────────────────────────────────────────────────────────────────┤
│                   RODATA SECTION (variable)                     │
├─────────────────────────────────────────────────────────────────┤
│                    ENTRY POINTS (4 bytes × N)                   │
│                    Address of each exported function            │
├─────────────────────────────────────────────────────────────────┤
│                    SYMBOL NAMES (variable)                      │
│                    Null-terminated strings for entry points     │
└─────────────────────────────────────────────────────────────────┘
```

**Notes:**
- All multi-byte fields are little-endian (Cortex-M4 is LE)
- `.bss` section is NOT transferred (zeroed by firmware on load)
- Entry points are offsets into `dynld_text_buf`, not absolute addresses

### 2.2 Symbol Resolution Table

Host maintains a mapping of firmware symbols to addresses from map file:

```python
firmware_symbols = {
    "printf": {
        "address": 0x08005432,
        "section": ".text",
        "type": "function"
    },
    "g_rgb_matrix_host_buf": {
        "address": 0x20010000,
        "section": ".data",
        "type": "variable"
    },
    # ... more symbols from map file
}
```

---

## 3. Component Design

### 3.1 ElfLoader Class

**File:** `ElfLoader.py` (new)

**Responsibilities:**
- Parse ELF sections (`.text`, `.data`, `.rodata`, `.bss`)
- Parse relocation entries (`.rel.text`, `.rel.dyn`)
- Resolve symbol references using firmware map file
- Patch `.text` section with resolved addresses
- Pack sections into transfer blob
- Return ElfModule object

**Interface:**
```python
class ElfLoader:
    def __init__(self, elf_path: str, map_file_path: str, 
                 dbg: DebugTracer = None)
    def load(self) -> ElfModule
    def _parse_elf(self)
    def _parse_relocations(self)
    def _apply_relocations(self)
    def _apply_relocation(self, data, rel, section_base)
    def _patch_thumb_bl(self, data, offset, target_addr, section_base)
    def _patch_thumb_branch(self, data, offset, target_addr, section_base)
    def _create_module(self) -> ElfModule
```

### 3.2 ElfModule Class

**File:** `ElfLoader.py` (new)

```python
class ElfModule:
    def __init__(self, text: bytes, data: bytes, rodata: bytes,
                 bss_size: int, symbols: dict)
    @property
    def total_size(self) -> int
    def validate(self, buffer_sizes: dict) -> None
```

### 3.3 KeybScriptEnv Extensions

**File:** `QMKataKeyboard.py` (extend `KeybScriptEnv`)

**Current Interface:**
```python
kb.compile("file.c") → {'elf': bytes, 'bin': bytes}
kb.exec(binary_blob) → return_value
```

**Extended Interface:**
```python
kb.compile("file.c") → ElfModule  # Full ELF with sections

kb.exec(module: ElfModule, entry_point: str) → int  # New mode
kb.exec(binary: bytes) → int  # Old mode (backward compat)
kb.exec(source: str, entry_point: str) → int  # Compile+exec
```

### 3.4 GccToolchain Extensions

**File:** `GccToolchain.py`

No major changes needed - existing `compile()` and `elf2bin()` methods work.
`ElfLoader` uses `pyelftools` directly for parsing.

### 3.5 Keyboard Model Extensions

**File:** `keyboards/KeychronQ3Max.py`

```python
class KeychronQ3Max:
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

---

## 4. Relocation System

### 4.1 ARM Relocation Types Supported

| R_Type | Constant | Use Case | Patching Logic |
|--------|----------|----------|----------------|
| `R_ARM_ABS32` | 2 | 32-bit absolute address | `*loc = *loc + value` |
| `R_ARM_THM_CALL` | 7 | THUMB BL instruction | Patch 26-bit target address |
| `R_ARM_THM_JUMP24` | 25 | THUMB B instruction | Patch 24-bit branch offset |

### 4.2 Relocation Algorithm

```
1. Parse ELF .rel.text / .rel.dyn sections
2. For each relocation entry:
   a. Get symbol name from symbol table
   b. Look up symbol in firmware map file
   c. Get address from map file
   d. Set THUMB bit (bit-0) for functions
   e. Apply relocation based on type:
      - ABS32: Add address to current value
      - THM_CALL: Patch BL instruction with new offset
      - THM_JUMP24: Patch B instruction with new offset
3. Return patched .text section
```

### 4.3 Example Relocation

Module code:
```c
extern int printf(const char* fmt, ...);

int test() {
    printf("Hello");  // BL printf instruction
    return 0;
}
```

ELF contains:
- `.text` with `BL` instruction at offset 0x10
- `.rel.text` with entry: `offset=0x10, type=R_ARM_THM_CALL, symbol=printf`

ElfLoader:
1. Reads relocation: need to patch offset 0x10 for symbol `printf`
2. Looks up `printf` in map file: address = 0x08005432
3. Sets THUMB bit: 0x08005433
4. Calculates offset from module's PC to target
5. Patches `BL` instruction with new immediate value

---

## 5. Execution Flow

### 5.1 Script-Side Flow

```python
# User script
module = kb.compile("my_module.c")  # Returns ElfModule
result = kb.exec(module, entry_point="my_function")
```

### 5.2 Internal Flow

```
1. kb.compile("my_module.c")
   ├─ GccToolchain.compile() → my_module.elf
   ├─ ElfLoader.load_elf() → parse sections
   ├─ ElfLoader._parse_relocations() → parse .rel.text
   ├─ ElfLoader._apply_relocations() → patch addresses
   └─ ElfLoader._create_module() → ElfModule

2. kb.exec(module, "my_function")
   ├─ ElfModule.validate(buffer_sizes)
   ├─ KeybScriptEnv._pack_module(module) → blob
   ├─ send_sysex(ID_DYNLD_FUNCTION, blob)
   ├─ send_sysex(ID_DYNLD_FUNEXEC, func_id, entry_addr)
   └─ wait_for_response() → return_value
```

### 5.3 Firmware-Side Flow

```c
1. Receive ID_DYNLD_FUNCTION
   ├─ Parse blob header
   ├─ Validate magic and version
   ├─ Copy .text → dynld_text_buf
   ├─ Copy .data → dynld_data_buf
   ├─ Copy .rodata → dynld_rodata_buf
   └─ Zero dynld_bss_buf

2. Receive ID_DYNLD_FUNEXEC
   ├─ Extract func_id and entry_addr
   ├─ Calculate function pointer: dynld_text_buf + entry_addr | 1
   └─ Execute and store return value

3. Send RESPONSE with return value
```

---

## 6. Error Handling

| Error Condition | Detection Point | Exception | Response |
|----------------|-----------------|-----------|----------|
| Symbol not found in map file | `_apply_relocation()` | `SymbolNotFoundError` | Clear message with available symbols |
| Section too large for buffer | `ElfModule.validate()` | `BufferOverflowError` | Show section size vs buffer size |
| Invalid ELF format | `_parse_elf()` | `InvalidELFError` | Show ELF class and machine type |
| Unsupported relocation type | `_apply_relocation()` | Warning (logged) | Skip relocation, continue |
| Firmware load fails | `send_sysex_wait()` | ConnectionError | Retry or abort |
| Execution timeout | `wait_for_response()` | `ExecutionTimeoutError` | Show timeout duration |
| Entry point not found | `exec()` | `SymbolNotFoundError` | List available entry points |

---

## 7. Testing Strategy

### 7.1 Test Cases

**Test 1: Simple function with no external deps**
```c
int add(int a, int b) { return a + b; }
```
Expected: Loads and executes, returns correct sum

**Test 2: Function calling printf**
```c
extern int printf(const char* fmt, ...);
int test_printf() {
    printf("Hello from loaded module\n");
    return 42;
}
```
Expected: `printf` resolved from map file, output visible on console

**Test 3: Module with global variables**
```c
static int counter = 0;       // .data
static int uninit;            // .bss
const char* msg = "Hi";       // .rodata

int increment() {
    counter++;
    return counter;
}
```
Expected: `.data` initialized, `.bss` zeroed, `.rodata` accessible

**Test 4: Module accessing firmware globals**
```c
extern uint8_t g_rgb_matrix_host_buf[];

void set_led(int index, uint32_t color) {
    g_rgb_matrix_host_buf[index*4] = color & 0xFF;
}
```
Expected: Firmware global accessible, RGB LEDs change

**Test 5: Buffer overflow detection**
```c
// Module with 10KB .text (exceeds 8KB buffer)
```
Expected: `BufferOverflowError` raised before transfer

**Test 6: Symbol not found**
```c
extern int nonexistent_function();
```
Expected: `SymbolNotFoundError` with helpful message

**Test 7: Backward compatibility**
```python
code = kb.compile("file.c")  # Returns dict
kb.exec(code['bin'])  # Old binary mode
```
Expected: Works as before

### 7.2 Hardware Testing

- [ ] Test on Keychron Q3 Max (STM32F402, Cortex-M4)
- [ ] Verify THUMB mode function calls
- [ ] Verify data section initialization
- [ ] Verify BSS zeroing
- [ ] Verify stack doesn't overflow
- [ ] Verify module can be loaded multiple times

---

## 8. Firmware Requirements

### 8.1 Pre-allocated Buffers

```c
// In qmk_firmware with addresses that appear in map file
__attribute__((section(".dynld_text")))
uint8_t dynld_text_buf[8192] __attribute__((aligned(8)));

__attribute__((section(".dynld_data")))  
uint8_t dynld_data_buf[2048] __attribute__((aligned(4)));

__attribute__((section(".dynld_rodata")))
uint8_t dynld_rodata_buf[1024] __attribute__((aligned(4)));

__attribute__((section(".dynld_bss")))
uint8_t dynld_bss_buf[1024] __attribute__((aligned(4)));
```

### 8.2 Extended Protocol Handler

```c
typedef struct {
    uint32_t magic;      // 0x454C464D
    uint32_t version;    // 0x00000001
    uint32_t text_size;
    uint32_t data_size;
    uint32_t rodata_size;
    uint32_t bss_size;
} __attribute__((packed)) dynld_header_t;

void dynld_handle_function(uint8_t* data, uint16_t len) {
    dynld_header_t* hdr = (dynld_header_t*)data;
    
    if (hdr->magic == 0x454C464D && hdr->version == 1) {
        // New format: multi-section blob
        uint8_t* src = (uint8_t*)(hdr + 1);
        
        memcpy(dynld_text_buf, src, hdr->text_size);
        src += hdr->text_size;
        
        memcpy(dynld_data_buf, src, hdr->data_size);
        src += hdr->data_size;
        
        memcpy(dynld_rodata_buf, src, hdr->rodata_size);
        src += hdr->rodata_size;
        
        memset(dynld_bss_buf, 0, hdr->bss_size);
        
        // Entry points follow (for future use)
    } else {
        // Old format: single binary blob
        memcpy(dynld_text_buf, data, len);
    }
    
    // Send acknowledgment
}

void dynld_handle_funexec(uint8_t* data, uint16_t len) {
    uint16_t func_id = data[0] | (data[1] << 8);
    uint32_t entry_addr = data[2] | (data[3] << 8) | 
                          (data[4] << 16) | (data[5] << 24);
    
    // For modules, entry_addr is offset into dynld_text_buf
    typedef uint32_t (*func_t)(void);
    func_t func = (func_t)((uint32_t)dynld_text_buf + entry_addr | 1);
    
    dynld_return_value = func();
    
    // Send response with return value
}
```

### 8.3 Map File Configuration

Firmware must be compiled with map file output:
```make
# In rules.mk or similar
MAP_FILE = $(BUILD_DIR)/firmware.map
LDFLAGS += -Map=$(MAP_FILE)
```

---

## 9. Migration Path

### Phase 1: Infrastructure (Days 1-2)
- [ ] Create `ElfLoader.py` with basic ELF parsing
- [ ] Add `DYNLD_BUFFER_SIZES` to keyboard models
- [ ] Add error classes (`SymbolNotFoundError`, etc.)

### Phase 2: Relocation System (Days 3-5)
- [ ] Implement `_parse_relocations()`
- [ ] Implement `_apply_relocation()` for ABS32
- [ ] Implement `_patch_thumb_bl()` for THM_CALL
- [ ] Implement `_patch_thumb_branch()` for THM_JUMP24
- [ ] Test with simple modules

### Phase 3: Module Packing (Days 6-7)
- [ ] Implement `ElfModule` class
- [ ] Implement `_pack_module()`
- [ ] Add validation against buffer sizes
- [ ] Test blob creation

### Phase 4: Integration (Days 8-9)
- [ ] Extend `KeybScriptEnv.compile()` to return ElfModule
- [ ] Extend `KeybScriptEnv.exec()` to handle both modes
- [ ] Add backward compatibility detection
- [ ] Update example scripts

### Phase 5: Firmware Updates (Days 10-12)
- [ ] Add pre-allocated buffers to firmware
- [ ] Extend `ID_DYNLD_FUNCTION` handler
- [ ] Extend `ID_DYNLD_FUNEXEC` handler
- [ ] Test on hardware

### Phase 6: Testing & Documentation (Days 13-14)
- [ ] Run all test cases
- [ ] Create example scripts
- [ ] Update README
- [ ] Document known limitations

---

## 10. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| ARM THUMB mode confusion | Crashes on function call | Medium | Always set bit-0 for functions; extensive testing |
| Stack overflow in module | Firmware crash | Medium | Limit module size; add watchdog timer |
| Buffer overflow | Memory corruption | Low | Validate sizes before copy; assert in firmware |
| Symbol resolution failures | Load failures | Medium | Clear error messages with suggestions |
| Endianness issues | Corrupt data | Low | Explicit little-endian packing throughout |
| Relocation patching bugs | Wrong addresses | Medium | Unit test each relocation type |
| Firmware map file outdated | Wrong symbol addresses | Medium | Check map file timestamp; warn if stale |
| Large modules timeout | Poor UX | Low | Progress feedback during load |

---

## Appendix A: File Structure

```
QMKata/
├── ElfLoader.py              # NEW: ELF parsing and symbol resolution
├── GccToolchain.py           # EXISTING: No changes needed
├── GccMapfile.py             # EXISTING: Used for symbol lookup
├── QMKataKeyboard.py         # EXTEND: KeybScriptEnv.compile()/exec()
├── keyboards/
│   ├── KeychronQ3Max.py      # EXTEND: Add DYNLD_BUFFER_SIZES
│   └── NuphyAir96V2.py       # EXTEND: Add DYNLD_BUFFER_SIZES
├── kb_scripts/
│   ├── kb_exec_fun.py        # EXISTING: Old binary mode
│   ├── kb_full_elf_simple.py # NEW: Basic ELF module example
│   ├── kb_full_elf_printf.py # NEW: Module with printf
│   └── kb_full_elf_data.py   # NEW: Module with .data/.bss
└── docs/
    └── plans/
        └── 2026-03-29-full-elf-loading-design.md  # This file
```

---

## Appendix B: Example Usage

### Basic Module

```python
# kb_scripts/kb_full_elf_example.py
module = kb.compile("my_module.c")
result = kb.exec(module, entry_point="my_function")
print(f"Result: {hex(result)}")
```

### Module with Firmware Dependencies

```python
# Module calls printf from firmware
module_c = '''
extern int printf(const char* fmt, ...);

int test() {
    printf("Hello from ELF module!\\n");
    return 0xDEADBEEF;
}
'''

with open("test.c", "w") as f:
    f.write(module_c)

module = kb.compile("test.c")
result = kb.exec(module, entry_point="test")
```

### Backward Compatible

```python
# Old style still works
code = kb.compile("file.c")  # Returns {'elf': ..., 'bin': ...}
result = kb.exec(code['bin'])  # Raw bytes → old mode
```

---

## Approval

- [x] Design reviewed
- [x] Key decisions confirmed (auto relocation, per-keyboard buffers, backward compat)
- [ ] Ready for implementation plan

**Next Step:** Invoke `writing-plans` skill to create detailed implementation plan.
