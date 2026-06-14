import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MURMURATION_SOURCE = ROOT / "dynld_animation_examples" / "kb_murmuration.c"


class MurmurationSourceContractTest(unittest.TestCase):
    def test_animation_uses_boids_contract_not_flow_field(self):
        source = MURMURATION_SOURCE.read_text()

        self.assertIn("BIRD_COUNT", source)
        self.assertIn("SEPARATION_RADIUS_Q8", source)
        self.assertIn("EDGE_MARGIN_Q8", source)
        self.assertIn("center_x", source)
        self.assertIn("avg_vx", source)
        self.assertIn("separate_x", source)

        self.assertNotIn("sin_lut", source)
        self.assertNotIn("q_sin", source)
        self.assertNotIn("q_cos", source)

    def test_animation_renders_density_cloud_instead_of_particle_pixels(self):
        source = MURMURATION_SOURCE.read_text()

        self.assertIn("for (int led = 0; led < RGB_MATRIX_LED_COUNT; led++)", source)
        self.assertIn("density", source)
        self.assertIn("anim_env->set_color_hsv(led, hsv)", source)

    def test_animation_has_independent_side_to_side_migration_target(self):
        source = MURMURATION_SOURCE.read_text()

        self.assertIn("SWEEP_SPEED_Q8", source)
        self.assertIn("target_x", source)
        self.assertIn("target_y", source)
        self.assertIn("travel_dir", source)
        self.assertIn("travel_dir = -travel_dir", source)
        self.assertIn("target_x +=", source)
        self.assertIn("target_x - b->x", source)


if __name__ == "__main__":
    unittest.main()
