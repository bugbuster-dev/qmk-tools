import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MURMURATION_SOURCE = ROOT / "dynld_animation_examples" / "kb_murmuration.c"


class MurmurationSourceContractTest(unittest.TestCase):
    def test_animation_uses_local_neighborhood_boids(self):
        source = MURMURATION_SOURCE.read_text()

        self.assertIn("BIRD_COUNT", source)
        self.assertIn("PERCEPTION_RADIUS", source)
        self.assertIn("SEPARATION_RADIUS_Q8", source)
        # Per-bird local accumulation, not a single global average.
        self.assertIn("count", source)
        self.assertIn("coh_x", source)
        self.assertIn("ali_x", source)
        self.assertIn("sep_x", source)

        self.assertNotIn("sin_lut", source)
        self.assertNotIn("q_sin", source)
        self.assertNotIn("q_cos", source)

    def test_animation_renders_density_cloud_instead_of_particle_pixels(self):
        source = MURMURATION_SOURCE.read_text()

        self.assertIn("for (int led = 0; led < RGB_MATRIX_LED_COUNT; led++)", source)
        self.assertIn("density", source)
        self.assertIn("anim_env->set_color_hsv(led, hsv)", source)

    def test_animation_migrates_side_to_side_via_cruise_bias(self):
        source = MURMURATION_SOURCE.read_text()

        # Migration is a velocity bias that reverses at the sides, not a
        # shared point attractor.
        self.assertIn("CRUISE_Q8", source)
        self.assertIn("travel_dir", source)
        self.assertIn("cruise_vx", source)
        # Reversal is driven by the flock center reaching a side margin.
        self.assertIn("travel_dir = -1", source)
        self.assertIn("travel_dir = 1", source)
        # The collapse-causing single-point goal seek must be gone.
        self.assertNotIn("goal_x", source)

    def test_animation_dims_physical_edges_to_avoid_turnaround_flicker(self):
        source = MURMURATION_SOURCE.read_text()

        edge_margin = int(re.search(r"#define EDGE_MARGIN_Q8 \((\d+) << 8\)", source).group(1))
        migrate_margin = int(re.search(r"#define MIGRATE_MARGIN_Q8 \((\d+) << 8\)", source).group(1))

        self.assertGreaterEqual(migrate_margin, edge_margin + 12)
        self.assertIn("EDGE_FADE_MARGIN", source)
        self.assertIn("MAX_DENSITY", source)
        self.assertIn("edge_scale", source)
        self.assertIn("density = (density * edge_scale) >> 8", source)


if __name__ == "__main__":
    unittest.main()
