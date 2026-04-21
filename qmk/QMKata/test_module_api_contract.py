import unittest
from pathlib import Path

from ModuleBuild import HOOK_NAMES


ROOT = Path(__file__).resolve().parent
MODULE_API = ROOT / "module_api.h"


class ModuleApiContractTest(unittest.TestCase):
    def test_hook_names_exclude_lifecycle_offsets(self):
        self.assertEqual(
            {
                "combo_should_trigger": 0,
                "process_combo_event": 1,
                "get_combo_term": 2,
                "get_combo_must_hold": 5,
                "get_combo_must_tap": 6,
                "get_combo_must_press_in_order": 7,
                "process_combo_key_release": 8,
                "process_combo_key_repress": 9,
                "combo_ref_from_layer": 10,
            },
            HOOK_NAMES,
        )

    def test_hook_indices_match_module_api_header(self):
        header = MODULE_API.read_text(encoding="ascii")
        expected_defines = {
            "MODULE_HOOK_COMBO_SHOULD_TRIGGER": 0,
            "MODULE_HOOK_PROCESS_COMBO_EVENT": 1,
            "MODULE_HOOK_GET_COMBO_TERM": 2,
            "MODULE_HOOK_INIT": 3,
            "MODULE_HOOK_DEINIT": 4,
            "MODULE_HOOK_GET_COMBO_MUST_HOLD": 5,
            "MODULE_HOOK_GET_COMBO_MUST_TAP": 6,
            "MODULE_HOOK_GET_COMBO_MUST_PRESS_IN_ORDER": 7,
            "MODULE_HOOK_PROCESS_COMBO_KEY_RELEASE": 8,
            "MODULE_HOOK_PROCESS_COMBO_KEY_REPRESS": 9,
            "MODULE_HOOK_COMBO_REF_FROM_LAYER": 10,
            "MODULE_HOOK_MAX": 16,
        }
        import re
        for name, expected in expected_defines.items():
            m = re.search(rf"#define\s+{name}\s+(\d+)", header)
            self.assertIsNotNone(m, f"{name} missing from module_api.h")
            self.assertEqual(expected, int(m.group(1)), f"{name} index mismatch")

    def test_module_api_uses_layout_compatible_stubs(self):
        header = MODULE_API.read_text(encoding="ascii")

        self.assertIn("typedef struct {", header)
        self.assertIn("uint8_t col;", header)
        self.assertIn("uint8_t row;", header)
        self.assertIn("} keypos_t;", header)
        self.assertIn("typedef enum keyevent_type_t {", header)
        self.assertIn("TICK_EVENT = 0", header)
        self.assertIn("DIP_SWITCH_OFF_EVENT = 6", header)
        self.assertIn("} keyevent_type_t;", header)
        self.assertIn("keypos_t key;", header)
        self.assertIn("uint16_t time;", header)
        self.assertIn("keyevent_type_t type;", header)
        self.assertIn("bool pressed;", header)
        self.assertIn("typedef struct keyrecord_t {", header)
        self.assertIn("keyevent_t event;", header)
        self.assertIn("uint16_t keycode;", header)
        self.assertIn("typedef uint16_t layer_state_t;", header)
        self.assertIn("extern layer_state_t layer_state;", header)
        self.assertIn("extern layer_state_t default_layer_state;", header)


if __name__ == "__main__":
    unittest.main()
