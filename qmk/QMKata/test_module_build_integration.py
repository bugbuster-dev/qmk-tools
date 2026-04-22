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
    [MODULE_HOOK_COMBO_SHOULD_TRIGGER] = combo_should_trigger,
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
        # v2 header is 40 bytes, hook table starts at 40
        magic = int.from_bytes(binary[0:4], "little")
        version = int.from_bytes(binary[4:6], "little")
        hook_table_off = int.from_bytes(binary[16:20], "little")
        reloc_off = int.from_bytes(binary[28:32], "little")
        reloc_count = int.from_bytes(binary[32:36], "little")
        crc = int.from_bytes(binary[36:40], "little")
        self.assertEqual(0x4D4F444C, magic)
        self.assertEqual(2, version)
        self.assertEqual(40, hook_table_off)
        # combo_layer_filter has no string literals -> reloc_count may be 0
        # (empty table -> reloc_off == 0 too; populated table -> both non-zero).
        self.assertGreaterEqual(reloc_count, 0)
        self.assertEqual(reloc_count == 0, reloc_off == 0,
            "reloc_off and reloc_count must be both zero or both nonzero")
        self.assertNotEqual(0, crc)  # computed CRC should not be zero

    def test_header_field_order_for_null_module(self):
        """Pin exact init_off and deinit_off values for null_module.

        Rationale (Task 1 review I3 carry-forward): _Static_assert on
        sizeof(module_header_t) catches header size drift, but cannot
        catch two same-typed fields being swapped between the C struct
        declaration order and the Python struct.pack format string.
        This test pins concrete VALUES for two adjacent uint32_t fields
        so a swap shows up immediately as a test failure.

        Expected values for null_module:
          - init_off = 145: the only function in the module is
            module_init. The linker script currently produces a
            104-byte .hook_table section (see the deferred linker-script
            finding in docs/plans/2026-04-22-module-runtime-relocations.md
            "Out of scope"): `. = 40 + 64;` is interpreted section-
            relative, so .hook_table spans VMA 40..144, leaving 40
            bytes of unused padding between the real hook slots
            (40..104) and .text. module_init therefore lands at
            VMA 144 and the Thumb bit is set on function pointers:
            144 | 1 = 145. **When the linker-script bug is fixed this
            assertion must be updated to 105** (104 | 1).
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
            145, init_off,
            "init_off must point at module_init at .text base (144) with Thumb bit set",
        )
        self.assertEqual(
            0, deinit_off,
            "null_module has no deinit hook; deinit_off must be 0",
        )

    def test_null_module_has_one_reloc_for_init_string(self):
        """null_module calls printf on one string literal. After the
        build, reloc_count should be 1 and the pointed-to word must
        match the link-time address of that string."""
        builder = ModuleBuild(
            GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=str(FIRMWARE_ROOT)),
            firmware_path=str(FIRMWARE_ROOT),
        )
        result = builder.build(str(NULL_MODULE))
        self.assertIsNotNone(result, builder.last_error)
        b = result["binary"]
        reloc_off = int.from_bytes(b[28:32], "little")
        reloc_count = int.from_bytes(b[32:36], "little")
        self.assertEqual(1, reloc_count, f"expected 1 reloc, got {reloc_count}")
        self.assertGreater(reloc_off, 104)  # past hook table
        self.assertLessEqual(reloc_off + 4, len(b))
        target_offset = int.from_bytes(b[reloc_off:reloc_off + 4], "little")
        # The target offset points at a literal-pool word. That word
        # holds the link-time-absolute address of the
        # "[mod] null_module init" string.
        word = int.from_bytes(b[target_offset:target_offset + 4], "little")
        # String must exist at `word` offset and begin with "[mod]"
        self.assertLess(word, len(b))
        self.assertEqual(b"[mod]", b[word:word + 5])


if __name__ == "__main__":
    unittest.main()
