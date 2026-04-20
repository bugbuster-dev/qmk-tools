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
            },
            HOOK_NAMES,
        )

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
