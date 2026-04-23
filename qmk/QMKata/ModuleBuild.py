import os
import re
import struct
import subprocess
import tempfile
import zlib

from GccToolchain import GccToolchain, CompilerOptions
from GccMapfile import GccMapfile


# Must match firmware module_loader.h
MODULE_HEADER_MAGIC   = 0x4D4F444C  # "MODL" as uint32 (bytes on disk: 4C 44 4F 4D)
MODULE_HEADER_VERSION = 2
MODULE_HEADER_SIZE    = 40
MODULE_HOOK_TABLE_OFF = 40  # Hook table immediately follows header
MODULE_HOOK_MAX       = 16
MODULE_FLASH_SLOT_SIZE = 0x1000

# Must match firmware module_flash.h. Duplicated rather than shared via
# a generated header to keep the build system simple; a mismatch would
# surface as a CRC failure on the device, which is loud and localised.
MODULE_FLASH_BASE = 0x08008000

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

            # Step 3.5: Extract R_ARM_ABS32 relocations (literal-pool
            # absolute addresses that must be rebased at load time) from
            # the linked ELF. Done here, before objcopy strips the reloc
            # sections, so _assemble() can append the reloc table to the
            # raw binary and populate reloc_off/reloc_count in the header.
            relocs = self._extract_relocations(elf_file)

            # Step 4: objcopy to binary
            if not self.toolchain.elf2bin(elf_file, bin_file):
                self.last_error = "objcopy failed"
                return None

            # Step 5: Read binary and detect hooks
            with open(bin_file, "rb") as f:
                raw_bin = f.read()

            # Step 6: Generate header and assemble final binary
            return self._assemble(raw_bin, relocs)

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

    def _extract_relocations(self, elf_file):
        """Extract R_ARM_ABS32 relocations targeting .text (literal pool).

        Returns a sorted list of byte offsets (into the final binary) where
        a 32-bit absolute address sits that must be rebased from link-time
        (ORIGIN=0) to runtime (slot_addr) by adding slot_addr.

        Relocations against .hook_table are filtered out because firmware
        dispatch already adds slot_addr to those offsets at call time.
        Other reloc types (R_ARM_THM_CALL etc.) are ignored because
        external symbols like printf are resolved at link time via the
        PROVIDE() symbol map.

        NOTE: the .text-only filter assumes module_linker.ld merges
        .rodata* into .text. If that changes (e.g. a separate .rodata
        output section is added), .rodata targets must be added here
        or literal-pool rebasing will silently break.
        """
        from elftools.elf.elffile import ELFFile
        from elftools.elf.relocation import RelocationSection
        from elftools.elf.enums import ENUM_RELOC_TYPE_ARM

        R_ARM_ABS32 = ENUM_RELOC_TYPE_ARM['R_ARM_ABS32']
        offsets = []
        with open(elf_file, "rb") as f:
            elf = ELFFile(f)
            # For ET_EXEC (our case — module_linker.ld produces an executable
            # with ORIGIN=0), r_offset is already the VMA, which for us
            # equals the file offset into the raw binary. For ET_REL we'd
            # add sh_addr, but we never link modules with -r.
            is_exec = elf['e_type'] == 'ET_EXEC'
            for sec in elf.iter_sections():
                if not isinstance(sec, RelocationSection):
                    continue
                target = elf.get_section(sec['sh_info'])
                if target.name != ".text":
                    # Skip .hook_table and any other targets. Hook-table
                    # relocations are intentionally offset-based.
                    continue
                base = 0 if is_exec else target['sh_addr']
                for r in sec.iter_relocations():
                    if r['r_info_type'] != R_ARM_ABS32:
                        continue
                    offsets.append(base + r['r_offset'])
        return sorted(offsets)

    def _assemble(self, raw_bin, relocs):
        """Assemble final module binary: replace header area + parse hook table.

        Appends the relocation table (one little-endian uint32 offset
        per entry, in the already-sorted order returned by
        _extract_relocations) directly after .text so that:
          - code_size in the header covers the reloc table too;
          - the CRC is computed over the full post-append binary;
          - the firmware loader can read `code_size` bytes from Flash,
            verify CRC, then walk the reloc table at `reloc_off`.

        An empty `relocs` list leaves both reloc_off and reloc_count
        at zero and does NOT append any bytes (no sentinel).
        """
        # The binary starts at offset 0:
        #   [0..39]    = header space (40 bytes, filled by linker with zeros)
        #   [40..143]  = .hook_table section (linker reserves 104 bytes due
        #                to section-relative `. = 40 + 64;` in module_linker.ld;
        #                only bytes 40..103 hold real hook slots, 104..143 is
        #                padding — see plan 2026-04-22 "Out of scope" for the
        #                deferred fix that would shrink this to 64 bytes)
        #   [144..]    = code (.text + merged .rodata), followed by reloc table

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

        # Append the reloc table BEFORE computing code_size / CRC, so
        # both cover the appended bytes. Offsets are already sorted
        # ascending by _extract_relocations; do not re-sort or reorder.
        # The linker script ends .text with ALIGN(4), so raw_bin length
        # must already be word-aligned — if this assertion ever fails,
        # a linker-script regression has broken the alignment invariant
        # the reloc table relies on (firmware reads 4-byte LE entries
        # starting at reloc_off and expects no padding between them).
        assert len(raw_bin) % 4 == 0, (
            f"raw_bin length {len(raw_bin)} not 4-aligned before reloc append; "
            "check module_linker.ld ALIGN(4) at end of .text"
        )
        if relocs:
            reloc_off = len(raw_bin)
            reloc_count = len(relocs)
            reloc_bytes = b"".join(struct.pack("<I", off) for off in relocs)
            raw_bin = raw_bin + reloc_bytes
        else:
            reloc_off = 0
            reloc_count = 0

        # Build 40-byte header matching firmware module_header_t layout:
        #   uint32_t magic;          // offset 0
        #   uint16_t version;        // offset 4
        #   uint16_t flags;          // offset 6
        #   uint32_t code_size;      // offset 8
        #   uint32_t hook_bitmap;    // offset 12
        #   uint32_t hook_table_off; // offset 16
        #   uint32_t init_off;       // offset 20
        #   uint32_t deinit_off;     // offset 24
        #   uint32_t reloc_off;      // offset 28 (0 = none)
        #   uint32_t reloc_count;    // offset 32
        #   uint32_t crc32;          // offset 36 (filled in below)
        header = struct.pack("<I H H I I I I I I I I",
            MODULE_HEADER_MAGIC,       # magic
            MODULE_HEADER_VERSION,     # version = 2
            0x0000,                    # flags: reserved (firmware ignores)
            len(raw_bin),              # code_size (includes reloc table)
            hook_bitmap,               # hook_bitmap
            MODULE_HOOK_TABLE_OFF,     # hook_table_off = 40
            init_off,                  # init_off
            deinit_off,                # deinit_off
            reloc_off,                 # reloc_off (0 if no relocs)
            reloc_count,               # reloc_count (0 if no relocs)
            0,                         # crc32 placeholder, patched below
        )
        assert len(header) == MODULE_HEADER_SIZE

        # Replace first MODULE_HEADER_SIZE bytes of binary with our header
        final_bin = bytearray(header) + raw_bin[MODULE_HEADER_SIZE:]

        # Compute CRC-32/ISO-HDLC (zlib-compatible) over the whole binary
        # with the 4-byte crc32 field held at zero, then patch the result
        # into the header. The firmware uses the same algorithm and the
        # same "crc field reads as zero during computation" convention,
        # so a match at load/boot time means accidental corruption of the
        # flashed bytes (transmission error, interrupted erase, bit rot)
        # is detected with ~2**-32 false-negative probability. This is
        # NOT an authenticity check — CRC-32 is trivially forgeable.
        # See validate_module_crc() in module_loader.c.
        crc_off = MODULE_HEADER_SIZE - 4
        assert bytes(final_bin[crc_off:crc_off + 4]) == b"\x00\x00\x00\x00"
        crc_value = zlib.crc32(bytes(final_bin)) & 0xFFFFFFFF
        struct.pack_into("<I", final_bin, crc_off, crc_value)
        final_bin = bytes(final_bin)

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
            'relocs': list(relocs),  # sorted ascending; apply_relocations_and_crc consumes
        }

    def apply_relocations_and_crc(self, binary, relocs, slot_addr):
        """Rebase ABS32 targets by slot_addr and embed the final CRC.

        Called from ModuleTab._prepare_binary_for_load at load time, once the
        user has picked a flash slot. Firmware writes these bytes verbatim
        and validates the embedded CRC on both module_load (RAM buffer copy)
        and module_boot_scan (XIP from flash). Because flash bytes equal
        these bytes, CRC matches on every cold boot.

        Arguments:
          binary:    bytes/bytearray from _assemble. The crc32 field may hold
                     a provisional value from _assemble; it is overwritten.
          relocs:    sorted list of u32 byte offsets into binary, as emitted
                     by _extract_relocations. Empty list means no literal-pool
                     ABS32 entries to rebase — still triggers a CRC recompute
                     because binary may have been mutated by the UI path
                     (hook_bitmap / init_off / deinit_off patches) before
                     reaching this helper.
          slot_addr: firmware MODULE_FLASH_GET_SLOT_ADDR(slot_id) equivalent,
                     i.e. MODULE_FLASH_BASE + slot_id * MODULE_FLASH_SLOT_SIZE.

        Returns a new bytes object. Does not mutate the input.
        """
        out = bytearray(binary)
        for off in relocs:
            if off + 4 > len(out):
                raise ValueError(
                    f"reloc offset {off} out of range (binary {len(out)} bytes)"
                )
            val = struct.unpack_from("<I", out, off)[0]
            struct.pack_into("<I", out, off, (val + slot_addr) & 0xFFFFFFFF)

        crc_off = MODULE_HEADER_SIZE - 4
        struct.pack_into("<I", out, crc_off, 0)
        crc_value = zlib.crc32(bytes(out)) & 0xFFFFFFFF
        struct.pack_into("<I", out, crc_off, crc_value)
        return bytes(out)
