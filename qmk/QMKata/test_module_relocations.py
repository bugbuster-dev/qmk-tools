import os, shutil, tempfile, unittest
from pathlib import Path

from GccToolchain import GccToolchain
from ModuleBuild import ModuleBuild
from keyboards.KeychronQ3Max import KeychronQ3Max

ROOT = Path(__file__).resolve().parent
FIRMWARE_ROOT = ROOT.parents[2] / "keychron_qmk_firmware"


@unittest.skipUnless(shutil.which("arm-none-eabi-gcc"), "requires ARM toolchain")
class ModuleRelocationsTest(unittest.TestCase):

    def _build_probe(self, tmpdir, source_lines):
        """Compile+link a probe module; return (elf_path, bin_bytes)."""
        src = '\n'.join([
            '#include "module_api.h"',
            'extern int printf(const char *fmt, ...);',
            *source_lines,
            'MODULE_HOOK_TABLE',
            'const void *module_hook_table[MODULE_HOOK_MAX] = {',
            '    [MODULE_HOOK_INIT] = module_init,',
            '};',
        ])
        src_path = Path(tmpdir) / "probe.c"
        src_path.write_text(src)
        tc = GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT))
        builder = ModuleBuild(tc, firmware_path=str(FIRMWARE_ROOT))
        obj = str(Path(tmpdir) / "probe.o")
        elf = str(Path(tmpdir) / "probe.elf")
        bin_ = str(Path(tmpdir) / "probe.bin")
        self.assertTrue(builder._compile(str(src_path), obj))
        sym_ld = str(Path(tmpdir) / "sym.ld")
        self.assertTrue(builder._resolve_symbols(obj, sym_ld))
        self.assertTrue(tc.link(obj, builder.linker_script, elf, [sym_ld]))
        self.assertTrue(tc.elf2bin(elf, bin_))
        return elf, Path(bin_).read_bytes()

    def test_extract_relocations_for_two_printf_literals(self):
        with tempfile.TemporaryDirectory() as td:
            elf, bin_bytes = self._build_probe(td, [
                'static uint32_t module_init(void) {',
                '    printf("[mod] hello world\\n");',
                '    printf("value=%u\\n", 42);',
                '    return MODULE_INIT_MAGIC;',
                '}',
            ])
            tc = GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT))
            builder = ModuleBuild(tc, firmware_path=str(FIRMWARE_ROOT))
            relocs = builder._extract_relocations(elf)
        # Exactly two R_ARM_ABS32 entries against .text (the two literal pool slots)
        self.assertEqual(2, len(relocs), f"expected 2 relocs, got {relocs}")
        # Offsets must be 4-byte aligned
        for off in relocs:
            self.assertEqual(0, off % 4, f"offset 0x{off:x} not word-aligned")
        # Offsets must fall within .text (i.e. >= hook_table_end = 104)
        # AND must index inside the emitted binary — not past its end.
        # This catches the class of bugs where offset arithmetic
        # double-counts section base vs r_offset (r_offset is already the
        # VMA for ET_EXEC output).
        for off in relocs:
            self.assertGreaterEqual(off, 104, f"offset 0x{off:x} overlaps header/hook_table")
            self.assertLessEqual(off + 4, len(bin_bytes),
                f"offset 0x{off:x} past bin end 0x{len(bin_bytes):x}")
            # Each patch site holds the link-time absolute address of a
            # string literal inside .text (merged .rodata). That address
            # must itself be a valid byte offset into the binary.
            word = int.from_bytes(bin_bytes[off:off+4], 'little')
            self.assertGreater(word, 0,
                f"patch site 0x{off:x} holds 0, expected link-time string address")
            self.assertLess(word, len(bin_bytes),
                f"patch site 0x{off:x} holds 0x{word:x} past bin end 0x{len(bin_bytes):x}")

    def test_extract_relocations_empty_for_no_literals(self):
        with tempfile.TemporaryDirectory() as td:
            elf, _ = self._build_probe(td, [
                'static uint32_t module_init(void) {',
                '    return MODULE_INIT_MAGIC;',
                '}',
            ])
            tc = GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT))
            builder = ModuleBuild(tc, firmware_path=str(FIRMWARE_ROOT))
            relocs = builder._extract_relocations(elf)
        self.assertEqual([], relocs)

    def test_extract_relocations_skips_hook_table(self):
        """Hook-table R_ARM_ABS32 entries must be filtered out — firmware
        still dispatches via offset + slot_addr, not via patched absolutes."""
        with tempfile.TemporaryDirectory() as td:
            elf, _ = self._build_probe(td, [
                'static uint32_t module_init(void) {',
                '    return MODULE_INIT_MAGIC;',
                '}',
            ])
            tc = GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT))
            builder = ModuleBuild(tc, firmware_path=str(FIRMWARE_ROOT))
            relocs = builder._extract_relocations(elf)
            # No relocs because the only ABS32 in this module is the
            # hook-table slot for module_init, which we must skip.
            self.assertEqual([], relocs)

    def test_emitted_relocs_are_data_not_thm_call(self):
        """Defense-in-depth: every emitted reloc offset must point at a
        literal-pool word (a plausible data pointer into the binary),
        NOT at a BL.W/BLX Thumb-2 instruction pair. The _extract_relocations
        filter already rejects R_ARM_THM_CALL (only R_ARM_ABS32 is kept),
        so this assertion should trivially hold — but it's a cheap guard
        against future refactors silently letting call-site relocations
        slip through into the runtime patch list.

        Encoding check (ARMv7-M T1 BL encoding, little-endian word read):
            low  halfword:  1111 0Sii iiii iiii  (bits 15..11 == 0b11110)
            high halfword:  11J1 Jiii iiii iiii  (bits 15,14,12 == 1;
                                                  bits 13 (J1), 11 (J2) vary)
        So: low halfword fixed mask = 0xF800 / value 0xF000.
            high halfword: (val & 0xD000) == 0xD000 (bits 15 and 12 set).
        We cannot use a single 32-bit mask because J1 varies — the previous
        mask-only test only caught ~25% of BL.W encodings. Do an explicit
        halfword decomposition instead.
        """
        builder = ModuleBuild(
            GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT)),
            firmware_path=str(FIRMWARE_ROOT),
        )
        null_src = ROOT / "module_examples" / "null_module.c"
        result = builder.build(str(null_src))
        self.assertIsNotNone(result, builder.last_error)
        b = result["binary"]
        reloc_off = int.from_bytes(b[28:32], "little")
        reloc_count = int.from_bytes(b[32:36], "little")
        self.assertGreater(reloc_count, 0,
            "null_module should emit at least one reloc; test is vacuous otherwise")
        for i in range(reloc_count):
            off = int.from_bytes(b[reloc_off + 4 * i:reloc_off + 4 * i + 4], "little")
            self.assertLessEqual(off + 4, len(b),
                f"reloc offset 0x{off:x} past bin end")
            word = int.from_bytes(b[off:off + 4], "little")
            self.assertLess(word, len(b),
                f"patch site word 0x{word:x} not a plausible in-binary data pointer")
            lo = word & 0xFFFF
            hi = (word >> 16) & 0xFFFF
            is_bl_w = ((lo & 0xF800) == 0xF000) and ((hi & 0xD000) == 0xD000)
            self.assertFalse(is_bl_w,
                f"patch site 0x{off:x} holds a BL.W instruction pair (word=0x{word:08x})")

    def test_apply_relocations_and_crc_rebases_and_finalises(self):
        """Host helper must rebase ABS32 targets by slot_addr and embed the
        final CRC so firmware sees identical bytes at load and boot scan.
        See docs/plans/2026-04-23-module-host-side-relocations.md Task 1."""
        import zlib
        import struct
        from ModuleBuild import ModuleBuild, MODULE_HEADER_SIZE, MODULE_FLASH_SLOT_SIZE

        # Firmware MODULE_FLASH_BASE; constant added to ModuleBuild in Task 2.
        MODULE_FLASH_BASE = 0x08008000

        builder = ModuleBuild(
            GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT)),
            firmware_path=str(FIRMWARE_ROOT),
        )
        null_src = ROOT / "module_examples" / "null_module.c"
        result = builder.build(str(null_src))
        self.assertIsNotNone(result, builder.last_error)

        # Task 2 will add 'relocs' to the result dict.
        self.assertIn('relocs', result)
        relocs = result['relocs']
        self.assertGreater(len(relocs), 0,
            "null_module has at least one literal-pool entry; empty relocs "
            "means _extract_relocations regressed or _assemble didn't pass "
            "them through")

        slot_id = 0
        slot_addr = MODULE_FLASH_BASE + slot_id * MODULE_FLASH_SLOT_SIZE

        # Snapshot pre-reloc target values.
        pre_targets = [
            struct.unpack_from("<I", result['binary'], off)[0]
            for off in relocs
        ]

        prepared = builder.apply_relocations_and_crc(
            result['binary'], relocs, slot_addr
        )

        # Each reloc target now holds (original + slot_addr) mod 2**32.
        for off, pre in zip(relocs, pre_targets):
            post = struct.unpack_from("<I", prepared, off)[0]
            self.assertEqual(post, (pre + slot_addr) & 0xFFFFFFFF,
                f"reloc at offset 0x{off:x}: expected 0x{(pre+slot_addr)&0xFFFFFFFF:08x}, "
                f"got 0x{post:08x}")

        # Stored CRC matches zlib.crc32 of prepared-with-crc-zeroed.
        crc_off = MODULE_HEADER_SIZE - 4
        stored_crc = struct.unpack_from("<I", prepared, crc_off)[0]
        verify = bytearray(prepared)
        struct.pack_into("<I", verify, crc_off, 0)
        computed_crc = zlib.crc32(bytes(verify)) & 0xFFFFFFFF
        self.assertEqual(stored_crc, computed_crc,
            f"prepared binary CRC mismatch: stored=0x{stored_crc:08x} "
            f"computed=0x{computed_crc:08x} (zlib.crc32 of prepared with "
            f"crc field zeroed)")


if __name__ == "__main__":
    unittest.main()
