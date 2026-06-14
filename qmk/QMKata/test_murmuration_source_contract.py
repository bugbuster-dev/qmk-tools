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
        self.assertIn("same_n", source)
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

    def test_animation_has_split_merge_dance(self):
        source = MURMURATION_SOURCE.read_text()

        # Integer oscillators drive a fission-fusion "dance" (no float/LUT).
        self.assertIn("tri8", source)
        self.assertIn("sep_osc", source)
        self.assertIn("axis_x", source)
        # Birds belong to one of two sub-flocks pulled apart and back together.
        self.assertIn("team", source)
        self.assertIn("dance_ax", source)

    def test_reverses_direction_when_center_reaches_edge(self):
        source = MURMURATION_SOURCE.read_text()

        # Reversal compares the flock center to a near-edge margin.
        self.assertIn("center_x > bound_x_q8 - MIGRATE_MARGIN_Q8", source)
        self.assertIn("center_x < MIGRATE_MARGIN_Q8", source)
        # The margin must be small enough that the center actually reaches
        # the edge zone before reversing (flock spread keeps it ~28px out).
        migrate_margin = int(re.search(r"#define MIGRATE_MARGIN_Q8 \((\d+) << 8\)", source).group(1))
        self.assertLessEqual(migrate_margin, 32)

    def test_animation_dims_physical_edges_to_avoid_turnaround_flicker(self):
        source = MURMURATION_SOURCE.read_text()

        self.assertIn("EDGE_FADE_MARGIN", source)
        self.assertIn("MAX_DENSITY", source)
        self.assertIn("edge_scale", source)
        self.assertIn("density = (density * edge_scale) >> 8", source)


if __name__ == "__main__":
    unittest.main()
