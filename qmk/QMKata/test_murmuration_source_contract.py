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


    def test_bird_state_uses_compact_q8_position_storage(self):
        source = MURMURATION_SOURCE.read_text()

        bird_struct = re.search(r"typedef struct \{(?P<body>.*?)\} bird_t;", source, re.S).group("body")
        self.assertIn("uint16_t x;", bird_struct)
        self.assertIn("uint16_t y;", bird_struct)
        self.assertNotIn("int32_t x;", bird_struct)
        self.assertNotIn("int32_t y;", bird_struct)


    def test_vertical_motion_uses_full_panel_height(self):
        source = MURMURATION_SOURCE.read_text()

        # Vertical split must be enabled so the dance can swing the
        # flock up and down across the matrix.
        self.assertIn("VERTICAL_OFFSET_MAX", source)
        vertical_offset = int(
            re.search(r"#define VERTICAL_OFFSET_MAX (\d+)", source).group(1))
        self.assertGreaterEqual(vertical_offset, 12)

        # The midline recentering and the per-bird pull toward mid_y are
        # both removed so birds aren't snapped back to the centre row.
        self.assertNotIn("MIDLINE_RECENTER_SHIFT", source)
        self.assertNotIn("mid_y - byp", source)
        self.assertNotRegex(
            source,
            r"next_y\s*\+=\s*\(\(\(int32_t\)mid_y\s*<<\s*8\)\s*-\s*next_y\)",
        )

        # Dance still uses mid_y as the vertical pivot via target_y.
        self.assertIn("target_y", source)
        self.assertIn("axis_y", source)
        self.assertIn("clamp_vertical_offset", source)

    def test_reinitializes_when_effect_runner_signals_init(self):
        source = MURMURATION_SOURCE.read_text()

        # QMK sets params->init=true when an RGB mode is (re)entered or
        # the matrix is re-enabled. The animation must honor that and
        # reseed flock state, not rely solely on a private static flag.
        self.assertRegex(
            source,
            r"if\s*\(\s*(?:params->init\s*\|\|\s*!initialized|!initialized\s*\|\|\s*params->init)\s*\)",
        )

    def test_brightness_scales_with_rgb_config_value(self):
        source = MURMURATION_SOURCE.read_text()

        # hsv.v must be scaled by the user's RGB matrix brightness
        # (rgb_config->hsv.v / 255), otherwise the brightness control
        # has no effect on this animation.
        self.assertIn("anim_env->rgb_config->hsv.v", source)
        self.assertRegex(
            source,
            r"\(\s*density\s*\*\s*anim_env->rgb_config->hsv\.v\s*\)\s*>>\s*8",
        )

    def test_skips_leds_whose_flags_do_not_match_params_flags(self):
        source = MURMURATION_SOURCE.read_text()

        # Standard QMK effects skip LEDs whose flag mask doesn't overlap
        # params->flags so users can keep underglow/indicators untouched.
        # The render loop must do the same check before writing each LED.
        self.assertIn("anim_env->led_config->flags[led]", source)
        self.assertIn("params->flags", source)
        # The check must guard the body of the per-LED render loop.
        self.assertRegex(
            source,
            r"for \(int led = 0; led < RGB_MATRIX_LED_COUNT; led\+\+\) \{"
            r"[^}]*?anim_env->led_config->flags\[led\][^}]*?params->flags",
        )

    def test_simulation_step_runs_only_on_first_iter_of_a_frame(self):
        source = MURMURATION_SOURCE.read_text()

        # The QMK matrix task slices a frame across multiple calls
        # (params->iter), but the boids simulation should advance once
        # per frame, not once per LED chunk. Gate the bird loop on
        # params->iter == 0 so simulation cost stays bounded.
        self.assertRegex(source, r"if\s*\(\s*params->iter\s*==\s*0\s*\)")
        # The per-bird update loop must live inside that gate.
        body = re.search(
            r"if\s*\(\s*params->iter\s*==\s*0\s*\)\s*\{(?P<body>.*?)\n    \}\n",
            source,
            re.S,
        )
        self.assertIsNotNone(body, "expected an `if (params->iter == 0) { ... }` block")
        self.assertIn("for (int i = 0; i < BIRD_COUNT; i++)", body.group("body"))

    def test_max_speed_is_modulated_by_dance_phase(self):
        source = MURMURATION_SOURCE.read_text()

        # The static MAX_SPEED_Q8 must be replaced by a min/max pair that
        # bounds the per-frame cur_max_speed_q8.
        self.assertIn("MAX_SPEED_MIN_Q8", source)
        self.assertIn("MAX_SPEED_MAX_Q8", source)
        self.assertNotRegex(source, r"#define\s+MAX_SPEED_Q8\b")

        min_v = int(re.search(r"#define MAX_SPEED_MIN_Q8 (\d+)", source).group(1))
        max_v = int(re.search(r"#define MAX_SPEED_MAX_Q8 (\d+)", source).group(1))
        self.assertLess(min_v, max_v,
                        "min must be below max so the cap actually breathes")

        # Per-frame cap derives from |sep_osc| so the dance and the speed
        # share a phase (slow at the split extreme, fast at the merge).
        self.assertIn("cur_max_speed_q8", source)
        # cur_max_speed_q8 and sep_osc should appear in the same small
        # span so the derivation is obviously a function of the dance.
        match = re.search(
            r"(?:cur_max_speed_q8[\s\S]{0,400}sep_osc"
            r"|sep_osc[\s\S]{0,400}cur_max_speed_q8)",
            source,
        )
        self.assertIsNotNone(
            match,
            "cur_max_speed_q8 and sep_osc must appear near each other "
            "so the speed cap clearly tracks the dance phase",
        )

        # clamp_speed takes the per-frame cap as a second argument so the
        # bird update uses the breathing limit instead of a static macro.
        self.assertRegex(
            source,
            r"clamp_speed\s*\(\s*b->vx\s*\+\s*ax\s*,\s*cur_max_speed_q8\s*\)",
        )
        self.assertRegex(
            source,
            r"clamp_speed\s*\(\s*b->vy\s*\+\s*ay\s*,\s*cur_max_speed_q8\s*\)",
        )


if __name__ == "__main__":
    unittest.main()
