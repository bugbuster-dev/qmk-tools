import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "dynld_animation_examples" / "kb_dynld_game_of_life.c"


class GameOfLifeSourceContractTest(unittest.TestCase):
    def test_animation_avoids_blocking_console_output(self):
        source = SOURCE.read_text()

        self.assertNotIn("mprintf", source)

    def test_seed_helper_is_not_nested_inside_entry_function(self):
        source = SOURCE.read_text()

        entry = re.search(
            r"bool\s+effect_runner_func\s*\([^)]*\)\s*\{(?P<body>.*)\n\}",
            source,
            re.S,
        ).group("body")
        self.assertNotIn("void do_seed", entry)

    def test_reinitializes_when_effect_runner_signals_init(self):
        source = SOURCE.read_text()

        self.assertRegex(
            source,
            r"if\s*\(\s*(?:params->init\s*\|\|\s*!seeded|!seeded\s*\|\|\s*params->init)\s*\)",
        )


if __name__ == "__main__":
    unittest.main()
