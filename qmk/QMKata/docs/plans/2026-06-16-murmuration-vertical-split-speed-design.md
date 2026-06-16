# Murmuration — Vertical Motion, Visible Split, Speed Modulation

## Problem

The current murmuration dynld animation
(`qmk/QMKata/dynld_animation_examples/kb_murmuration.c`) has three
visible-on-hardware shortcomings:

1. **No vertical motion.** `VERTICAL_OFFSET_MAX == 0` zeroes the
   dance's vertical component, and `next_y` is pulled back toward
   `mid_y` every frame at `>> 3` strength. The combination is stronger
   than `MAX_SPEED_Q8 = 150` (~0.59 px/frame), so the flock sits on the
   middle row.

2. **Split into two flocks is invisible.** Teams aim at
   `center_x ± off_x` with `off_x <= 32 px`, but the render kernel is
   ~36 px wide (`RENDER_RADIUS = 18`). The two clouds blend into one
   smear.

3. **Speed is fixed.** Nothing modulates `MAX_SPEED_Q8` or
   `CRUISE_Q8`, so the flock has the same drift speed at all times. No
   visible acceleration / deceleration.

## Goals

- Birds use the full panel height (0..cached_max_y) instead of being
  pinned to the midline.
- At the dance's split-extreme, two distinct cloud blobs are visible,
  separated by a clear dark gap.
- Speed visibly breathes between a slow and a fast range, synchronised
  to the existing dance cycle: slow at the split extremes, fast at the
  merge moment.

## Non-Goals

- No new statics, no new state across frames beyond what already exists.
- No change to the `params->init` / `params->iter` / `params->flags` /
  `rgb_config->hsv.v` fixes from the previous commit.
- No firmware change; the dynld slot is already 2048 B and current
  build is 1348 B (700 B headroom).

## Design

All three changes stay inside `effect_runner_func`. Public shape
(`bird_t`, `BIRD_COUNT`, iter==0 simulation gate, env-respecting render
loop) is preserved.

### Constants

| Constant                | Before | After | Why                                                      |
|-------------------------|--------|-------|----------------------------------------------------------|
| `MAX_SPEED_Q8`          | 150    | (removed)             | Replaced by per-frame `cur_max_speed_q8`     |
| `MAX_SPEED_MIN_Q8`      | (new)  | 80                    | Slow extreme: ~0.31 px/frame                 |
| `MAX_SPEED_MAX_Q8`      | (new)  | 220                   | Fast extreme: ~0.86 px/frame                 |
| `VERTICAL_OFFSET_MAX`   | 0      | 16                    | Half of the matrix half-height               |
| `SPLIT_OFFSET_MAX`      | 32     | 56                    | Two clouds end up ~112 px apart at peak      |
| `RENDER_RADIUS`         | 18     | 12                    | Smaller per-bird kernel; dark gap is visible |
| `MIDLINE_RECENTER_SHIFT`| 3      | (removed)             | Pull is gone entirely                        |

### Vertical motion

- Re-introduce `axis_y = tri8(aph + 64)` and
  `off_y = clamp_vertical_offset((split * axis_y) >> SPLIT_OFFSET_SHIFT)`
  with `clamp_vertical_offset` capped at ±`VERTICAL_OFFSET_MAX`.
- `target_y = mid_y + team * off_y` (already in the source, currently
  evaluates to `mid_y` because `off_y == 0`).
- Delete the `((mid_y - byp) >> 2)` recentering term from the `ay`
  computation.
- Delete the `next_y += ((mid_y<<8) - next_y) >> MIDLINE_RECENTER_SHIFT`
  line.
- The existing edge-force terms (`if (b->y < EDGE_MARGIN_Q8) ay += ...`)
  and the position clamps at `next_y < 0` / `next_y > bound_y_q8` keep
  birds inside the matrix.

### Visible split

- `SPLIT_OFFSET_MAX` 32 → 56 increases peak split distance from ~64 px
  to ~112 px.
- `RENDER_RADIUS` 18 → 12 shrinks the per-bird kernel.
- Rebalance the contrib formula in the render loop so the smaller
  kernel still produces usable brightness:
  - Old: `contrib = 72 - (dist_sq >> 2)` — peaks at 72, hits 0 at
    `dist_sq = 288`, but capped at `RENDER_RADIUS_SQ = 324`.
  - New: `contrib = 50 - (dist_sq >> 3)` — peaks at 50, hits 0 at
    `dist_sq = 400`, gated by `RENDER_RADIUS_SQ = 144`.
- `MAX_DENSITY = 220` stays; brightness scaling by `rgb_config->hsv.v`
  is unchanged.

### Speed modulation

Per frame, before the bird loop:

```c
/* |sep_osc| is ~128 when fully split open or shut and 0 when crossing
 * zero — invert it so the speed cap peaks at the merge moment and
 * troughs while the flocks are fully separated. */
int16_t abs_sep = sep_osc >= 0 ? sep_osc : -sep_osc;
uint8_t merge_phase = (uint8_t)(128 - abs_sep);  /* 0..128 */
int16_t cur_max_speed_q8 = MAX_SPEED_MIN_Q8 +
    (int16_t)(((uint32_t)merge_phase *
               (MAX_SPEED_MAX_Q8 - MAX_SPEED_MIN_Q8)) >> 7);
```

- `clamp_speed` takes the cap as a second argument: `clamp_speed(v, cur_max_speed_q8)`.
- That's the only call site, so the change is local.
- Sync with the dance: at the split extremes the flock visibly slows
  before reversing; at the merge moment it accelerates through.

### Tests (`test_murmuration_source_contract.py`)

| Action | Test                                                                    |
|--------|-------------------------------------------------------------------------|
| **Drop** | `test_vertical_motion_stays_inside_six_row_matrix` (midline pull is intentionally gone) |
| **Add**  | `test_vertical_motion_uses_full_panel_height` — pins `VERTICAL_OFFSET_MAX >= 12`, asserts the recentering term is gone |
| **Add**  | `test_split_clouds_are_visibly_separated` — pins `SPLIT_OFFSET_MAX >= 48` and `RENDER_RADIUS <= 14` |
| **Add**  | `test_max_speed_is_modulated_by_dance_phase` — pins both `MAX_SPEED_MIN_Q8` and `MAX_SPEED_MAX_Q8` exist with `MIN < MAX`, that `clamp_speed` takes a second arg, and that the per-frame derivation references `sep_osc` |
| **Keep** | All other 11 tests pass unchanged                                       |

### Size budget

- Cap: 2048 B. Pre-change: 1348 B. Headroom: 700 B.
- New ops per frame: 2 extra `tri8` calls (re-add `axis_y`), one abs,
  one UMULL+shift for `cur_max_speed_q8`, one extra arg threaded
  through `clamp_speed`.
- Removed ops: the `next_y +=` recentering, the `(mid_y - byp) >> 2`
  term.
- Expected net `.text` change: < +80 B. Verify after the build.

## Risks and Trade-offs

1. **Flock can sit on the edge.** Without the midline pull, the dance
   can park the flock near row 0 or row 5 for half a cycle. The user
   explicitly picked "aggressive" vertical, so this is the intended
   trade-off. Fallback if it looks bad on hardware: re-add the pull at
   strength `>> 5` (very weak) so it only dampens long-term drift.
2. **`abs_sep` on int16.** `sep_osc` is `tri8(ph)` which returns
   [-128, 128]. `-(-128)` is fine in `int16_t` arithmetic (no signed
   overflow), so the abs is safe.
3. **Render rebalance changes brightness curve shape.** Brighter near
   the centre of each blob, but `density` is still capped at
   `MAX_DENSITY = 220` before the brightness scale, so peak LED value
   is unchanged.

## Verification

1. `python3 -m unittest qmk.QMKata.test_murmuration_source_contract` —
   all tests (3 added, 1 removed, 11 kept) pass.
2. `python3 build_check.py` (with the same `/tmp/opencode/...`
   includes as the prior fix session) — binary size reported,
   confirmed under 2048 B.
3. On-hardware confirmation by the user: flock visibly uses multiple
   rows, two distinct clouds visible at the split extremes, speed
   visibly breathes.
