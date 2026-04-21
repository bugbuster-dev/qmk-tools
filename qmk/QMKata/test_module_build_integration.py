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


if __name__ == "__main__":
    unittest.main()
