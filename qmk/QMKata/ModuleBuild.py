import os
import re
import struct
import subprocess
import tempfile

from GccToolchain import GccToolchain, CompilerOptions
from GccMapfile import GccMapfile


# Must match firmware module_loader.h
MODULE_HEADER_MAGIC   = 0x4D4F444C  # "MODL" as uint32 (bytes on disk: 4C 44 4F 4D)
MODULE_HEADER_VERSION = 1
MODULE_HEADER_SIZE    = 32
MODULE_HOOK_TABLE_OFF = 32  # Hook table immediately follows header
MODULE_HOOK_MAX       = 16
MODULE_FLASH_SLOT_SIZE = 0x1000

# Hook name → index mapping (human-readable)
HOOK_NAMES = {
    'combo_should_trigger':         0,
    'process_combo_event':          1,
    'get_combo_term':               2,
    'get_combo_must_hold':          5,
    'get_combo_must_tap':           6,
    'get_combo_must_press_in_order': 7,
    'process_combo_key_release':    8,
    'process_combo_key_repress':    9,
    'combo_ref_from_layer':         10,
}

RESERVED_HOOK_NAMES = {
    'init': 3,
    'deinit': 4,
}

DISPLAY_HOOK_NAMES = {**HOOK_NAMES, **RESERVED_HOOK_NAMES}


def hook_name_for_index(index):
    for name, idx in DISPLAY_HOOK_NAMES.items():
        if idx == index:
            return name
    return f"hook_{index}"


def hook_index_for_name(name):
    hook_idx = DISPLAY_HOOK_NAMES.get(name)
    if hook_idx is not None:
        return hook_idx
    if name.startswith("hook_"):
        try:
            return int(name.split("_", 1)[1])
        except ValueError:
            return None
    return None


class ModuleBuild:
    """Build pipeline for loadable keyboard modules.
    
    Pipeline: compile (.c → .o) → resolve symbols → link (.o → .elf) → 
              objcopy (.elf → .bin) → prepend header → final binary
    """

    def __init__(self, toolchain, mapfile=None, firmware_path=None):
        """
        Args:
            toolchain: GccToolchain instance
            mapfile: GccMapfile instance (for external symbol resolution)
            firmware_path: path to QMK firmware root (for auto-discovering .map file)
        """
        self.toolchain = toolchain
        self.mapfile = mapfile
        if not self.mapfile and firmware_path:
            try:
                self.mapfile = GccMapfile(firmware_path=firmware_path)
            except Exception:
                pass
        self.last_error = None
        self.module_api_header = os.path.join(os.path.dirname(__file__), "module_api.h")
        self.linker_script = os.path.join(os.path.dirname(__file__), "module_linker.ld")

    def build(self, source_file):
        """Build a module from C source file.
        
        Args:
            source_file: path to .c source file
            
        Returns:
            dict with keys:
                'binary': bytes - complete module binary (header + hook table + code)
                'hook_bitmap': int - bitmask of hooks this module provides
                'hooks': list of str - human-readable hook names
                'size': int - total binary size
            or None on failure
        """
        self.last_error = None

        with tempfile.TemporaryDirectory(prefix="module_build_") as tmpdir:
            base_name = os.path.splitext(os.path.basename(source_file))[0]
            obj_file = os.path.join(tmpdir, base_name + ".o")
            elf_file = os.path.join(tmpdir, base_name + ".elf")
            bin_file = os.path.join(tmpdir, base_name + ".bin")

            # Step 1: Compile with module-specific options
            if not self._compile(source_file, obj_file):
                self.last_error = "compile failed"
                return None

            # Step 1.5: Reject writable module sections (.data/.bss/etc.)
            if not self._validate_no_writable_sections(obj_file):
                return None

            # Step 2: Resolve external symbols → generate symbol .ld file
            sym_ld_file = os.path.join(tmpdir, "symbols.ld")
            if not self._resolve_symbols(obj_file, sym_ld_file):
                return None

            # Step 3: Link
            extra_ld = [sym_ld_file] if os.path.exists(sym_ld_file) else None
            if not self.toolchain.link(obj_file, self.linker_script, elf_file, extra_ld):
                self.last_error = "link failed"
                return None

            # Step 4: objcopy to binary
            if not self.toolchain.elf2bin(elf_file, bin_file):
                self.last_error = "objcopy failed"
                return None

            # Step 5: Read binary and detect hooks
            with open(bin_file, "rb") as f:
                raw_bin = f.read()

            # Step 6: Generate header and assemble final binary
            return self._assemble(raw_bin)

    def _compile(self, source_file, obj_file):
        """Compile with module-specific options (no -fPIC, add -ffreestanding)."""
        opts = CompilerOptions()
        # Core ARM options
        opts.options([
            "-c",
            "-mcpu=cortex-m4",
            "-mthumb",
            "-mfloat-abi=hard",
            "-mfpu=fpv4-sp-d16",
            "-Os",
            "-ffreestanding",
            "-ffunction-sections",
            "-fdata-sections",
            "-fno-common",
            # Suppress exception unwind metadata. The module linker script
            # discards .ARM.exidx/.ARM.extab, so any compiler-emitted
            # unwind references would become dangling at runtime. These
            # flags guarantee no such metadata is generated in the first
            # place, preventing undefined behavior if module code ever
            # pulls in helpers that touch the unwind tables.
            "-fno-unwind-tables",
            "-fno-asynchronous-unwind-tables",
            "-fno-exceptions",
            "-Wall",
            "-Werror",
            "-std=gnu11",
        ])
        # Include path for module_api.h
        api_dir = os.path.dirname(self.module_api_header)
        opts.includes([api_dir + os.sep])

        return self.toolchain.compile(source_file, obj_file, opts)

    def _resolve_symbols(self, obj_file, sym_ld_file):
        """Find undefined symbols in object file, resolve from firmware .map file.
        
        Generates a linker script defining resolved symbol addresses.
        Returns True on success, False on failure (unresolvable symbols).
        """
        # Get undefined symbols using nm -u
        nm_tool = self.toolchain.tool.get("nm")
        if not nm_tool:
            print("E: nm tool not found in toolchain")
            self.last_error = "symbol resolution failed"
            return False
        try:
            result = subprocess.run(
                [nm_tool, "-u", obj_file],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"E: nm failed: {e}")
            self.last_error = "symbol resolution failed"
            return False

        undefined = []
        for line in result.stdout.decode().strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # nm -u output: "         U symbol_name"
            parts = line.split()
            if len(parts) >= 2 and parts[-2] == 'U':
                undefined.append(parts[-1])
            elif len(parts) == 1:
                # some nm versions just print the symbol name
                undefined.append(parts[0])

        if not undefined:
            # No undefined symbols — write empty file
            with open(sym_ld_file, 'w') as f:
                f.write("/* No external symbols */\n")
            return True

        if not self.mapfile:
            print(f"E: module has undefined symbols but no .map file for resolution: {undefined}")
            self.last_error = "symbol resolution failed"
            return False

        # Resolve each symbol
        resolved = []
        unresolved = []
        for sym in undefined:
            addr = None
            if sym in self.mapfile.variables:
                addr = self.mapfile.variables[sym]['address']
            elif sym in self.mapfile.functions:
                addr = self.mapfile.functions[sym]['address']

            if addr is not None:
                resolved.append((sym, addr))
            else:
                unresolved.append(sym)

        if unresolved:
            print(f"E: cannot resolve symbols: {unresolved}")
            self.last_error = "symbol resolution failed"
            return False

        # Write linker script with PROVIDE directives
        with open(sym_ld_file, 'w') as f:
            f.write("/* Auto-resolved external symbols from firmware .map */\n")
            for sym, addr in resolved:
                f.write(f"PROVIDE({sym} = {hex(addr)});\n")

        return True

    def _validate_no_writable_sections(self, obj_file):
        """Reject module objects containing writable global/static sections."""
        objdump_tool = self.toolchain.tool.get("objdump")
        if not objdump_tool:
            self.last_error = "module section validation failed"
            return False

        try:
            result = subprocess.run(
                [objdump_tool, "-h", obj_file],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"E: objdump section inspection failed: {e}")
            self.last_error = "module section validation failed"
            return False

        writable_prefixes = (".data", ".bss", ".sdata", ".sbss", ".tdata", ".tbss")
        offenders = []
        section_line = re.compile(r"^\s*\d+\s+(\S+)\s+([0-9A-Fa-f]+)\s+")

        for line in result.stdout.decode().splitlines():
            m = section_line.match(line)
            if not m:
                continue

            sec_name = m.group(1)
            sec_size = int(m.group(2), 16)
            if sec_size == 0:
                continue

            if sec_name.startswith(writable_prefixes):
                offenders.append((sec_name, sec_size))

        if offenders:
            names = ", ".join(f"{name}(0x{size:x})" for name, size in offenders)
            self.last_error = f"module contains writable sections: {names}"
            return False

        return True

    def _assemble(self, raw_bin):
        """Assemble final module binary: replace header area + parse hook table."""
        # The binary starts at offset 0:
        #   [0..31]   = header space (32 bytes, filled by linker with zeros)
        #   [32..95]  = hook table (16 * 4 = 64 bytes)
        #   [96..]    = code (.text + .rodata)

        if len(raw_bin) < MODULE_HEADER_SIZE + MODULE_HOOK_MAX * 4:
            print(f"E: binary too small ({len(raw_bin)} bytes)")
            self.last_error = "binary too small"
            return None

        # Read hook table to determine hook_bitmap
        hook_table_data = raw_bin[MODULE_HOOK_TABLE_OFF:MODULE_HOOK_TABLE_OFF + MODULE_HOOK_MAX * 4]
        hook_bitmap = 0
        init_off = 0
        deinit_off = 0
        hooks = []
        for i in range(MODULE_HOOK_MAX):
            offset_val = struct.unpack_from("<I", hook_table_data, i * 4)[0]
            if offset_val != 0:
                hook_bitmap |= (1 << i)
                hooks.append(hook_name_for_index(i))
                if i == 3:
                    init_off = offset_val
                elif i == 4:
                    deinit_off = offset_val

        # Build 32-byte header matching firmware module_header_t layout:
        #   uint32_t magic;          // offset 0
        #   uint16_t version;        // offset 4
        #   uint16_t flags;          // offset 6
        #   uint32_t code_size;      // offset 8
        #   uint32_t hook_bitmap;    // offset 12
        #   uint32_t hook_table_off; // offset 16
        #   uint32_t init_off;       // offset 20
        #   uint32_t deinit_off;     // offset 24
        #   uint32_t reserved;       // offset 28
        header = struct.pack("<I H H I I I I I I",
            MODULE_HEADER_MAGIC,       # magic
            MODULE_HEADER_VERSION,     # version
            0x0000,                    # flags: reserved (firmware ignores)
            len(raw_bin),              # code_size
            hook_bitmap,               # hook_bitmap
            MODULE_HOOK_TABLE_OFF,     # hook_table_off
            init_off,                  # init_off
            deinit_off,                # deinit_off
            0,                         # reserved
        )
        assert len(header) == MODULE_HEADER_SIZE

        # Replace first 32 bytes of binary with our header
        final_bin = header + raw_bin[MODULE_HEADER_SIZE:]
        fits_slot = len(final_bin) <= MODULE_FLASH_SLOT_SIZE

        if not fits_slot:
            self.last_error = (
                f"module binary exceeds slot size "
                f"({len(final_bin)} > {MODULE_FLASH_SLOT_SIZE})"
            )
            return None

        return {
            'binary': final_bin,
            'hook_bitmap': hook_bitmap,
            'hooks': hooks,
            'size': len(final_bin),
            'fits_slot': fits_slot,
        }
