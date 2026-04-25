import shutil
import tempfile
import unittest
from pathlib import Path

from GccToolchain import GccToolchain
from ModuleBuild import ModuleBuild
from keyboards.KeychronQ3Max import KeychronQ3Max


ROOT = Path(__file__).resolve().parent
FIRMWARE_ROOT = ROOT.parents[2] / "keychron_qmk_firmware"
EXAMPLE_MODULE = ROOT / "module_examples" / "combo_layer_filter.c"
NULL_MODULE = ROOT / "module_examples" / "null_module.c"


@unittest.skipUnless(shutil.which("arm-none-eabi-gcc"), "requires ARM toolchain")
class ModuleBuildIntegrationTest(unittest.TestCase):
    def test_example_module_build_reports_combo_hook(self):
        builder = ModuleBuild(
            GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT)),
            firmware_path=str(FIRMWARE_ROOT),
        )

        result = builder.build(str(EXAMPLE_MODULE))

        self.assertIsNotNone(result, builder.last_error)
        self.assertIn("combo_should_trigger", result["hooks"])
        self.assertEqual(1, result["hook_bitmap"] & 0x1)

    def test_module_with_writable_global_is_rejected_before_link(self):
        builder = ModuleBuild(
            GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT)),
            firmware_path=str(FIRMWARE_ROOT),
        )

        src = """
#include \"module_api.h\"
static uint32_t counter;
bool combo_should_trigger(uint16_t combo_index, combo_t *combo,
                          uint16_t keycode, keyrecord_t *record) {
    (void)combo_index; (void)combo; (void)keycode; (void)record;
    counter++;
    return true;
}
MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_COMBO_HOOK_SHOULD_TRIGGER] = combo_should_trigger,
};
"""

        with tempfile.TemporaryDirectory(prefix="module_writable_") as tmpdir:
            src_path = Path(tmpdir) / "bad_module.c"
            src_path.write_text(src)
            result = builder.build(str(src_path))

        self.assertIsNone(result)
        self.assertIsNotNone(builder.last_error)
        self.assertIn("writable sections", builder.last_error)

    def test_header_layout_v2(self):
        builder = ModuleBuild(
            GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT)),
            firmware_path=str(FIRMWARE_ROOT),
        )
        result = builder.build(str(EXAMPLE_MODULE))
        self.assertIsNotNone(result, builder.last_error)
        binary = result["binary"]
        # v2 header is 32 bytes, hook table starts at 32
        magic = int.from_bytes(binary[0:4], "little")
        version = int.from_bytes(binary[4:6], "little")
        hook_table_off = int.from_bytes(binary[16:20], "little")
        crc = int.from_bytes(binary[28:32], "little")
        self.assertEqual(0x4D4F444C, magic)
        self.assertEqual(2, version)
        self.assertEqual(32, hook_table_off)
        self.assertNotEqual(0, crc)  # provisional CRC should not be zero
        # Relocations are now returned in result['relocs'], not appended
        # to the binary. combo_layer_filter has no string literals, so
        # the list may be empty or non-empty depending on inlining —
        # assert only that the key exists.
        self.assertIn("relocs", result)

    def test_header_field_order_for_null_module(self):
        """Pin exact init_off and deinit_off values for null_module.

        Rationale: _Static_assert on sizeof(module_header_t) catches
        header size drift but cannot catch two same-typed fields being
        swapped between the C struct declaration order and the Python
        struct.pack format string. This test pins concrete VALUES for
        two adjacent uint32_t fields so a swap shows up immediately as
        a test failure.

        Expected values for null_module:
          - init_off = 161: the only function in the module is
            module_init. The linker script produces a 128-byte
            .hook_table section (MODULE_HOOK_MAX * 4), packed right
            after the 32-byte header, so .text starts at VMA 160.
            module_init lands at .text base (VMA 160) and the Thumb
            bit is set on function pointers: 160 | 1 = 161.
          - deinit_off = 0: null_module declares no deinit hook, so
            the hook table slot at MODULE_HOOK_DEINIT stays NULL and
            _assemble() leaves deinit_off unset.
        """
        builder = ModuleBuild(
            GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT)),
            firmware_path=str(FIRMWARE_ROOT),
        )
        result = builder.build(str(NULL_MODULE))
        self.assertIsNotNone(result, builder.last_error)
        binary = result["binary"]
        init_off = int.from_bytes(binary[20:24], "little")
        deinit_off = int.from_bytes(binary[24:28], "little")
        self.assertEqual(
            161, init_off,
            "init_off must point at module_init at .text base (160) with Thumb bit set",
        )
        self.assertEqual(
            0, deinit_off,
            "null_module has no deinit hook; deinit_off must be 0",
        )

    def test_null_module_has_one_reloc_for_init_string(self):
        """null_module calls mprintf on one string literal. After the
        build, result['relocs'] should have exactly one entry and the
        pointed-to word must match the link-time address of that string.
        The "[mod] " prefix is added at runtime by the firmware's
        mprintf implementation, not at build time, so the literal in
        the binary is just the user-supplied format string."""
        builder = ModuleBuild(
            GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT)),
            firmware_path=str(FIRMWARE_ROOT),
        )
        result = builder.build(str(NULL_MODULE))
        self.assertIsNotNone(result, builder.last_error)
        b = result["binary"]
        relocs = result["relocs"]
        self.assertEqual(1, len(relocs), f"expected 1 reloc, got {relocs}")
        reloc_off = relocs[0]
        self.assertGreater(reloc_off, 160)  # past hook table (32-byte hdr + 128-byte table)
        self.assertLessEqual(reloc_off + 4, len(b))
        # The reloc site holds a literal-pool word: the link-time-absolute
        # address of the "null_module init\n" string. Because the
        # module is linked at ORIGIN=0, that address is also the offset
        # into the binary where the string bytes live.
        string_off = int.from_bytes(b[reloc_off:reloc_off + 4], "little")
        self.assertLess(string_off, len(b))
        self.assertEqual(b"null_module init", b[string_off:string_off + 16])


if __name__ == "__main__":
    unittest.main()
