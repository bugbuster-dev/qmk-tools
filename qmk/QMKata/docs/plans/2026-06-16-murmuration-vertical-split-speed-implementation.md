# Murmuration Vertical / Split / Speed Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the murmuration RGB animation use the full panel height, render two visibly distinct sub-flocks at the dance extreme, and breathe its top speed between a slow and fast range synced to the dance cycle.

**Architecture:** All changes live inside `qmk/QMKata/dynld_animation_examples/kb_murmuration.c`. The simulation step's iter==0 gate, the env-respecting render loop, and `bird_t`/`BIRD_COUNT` are preserved. Three local edits: replace the static `MAX_SPEED_Q8` with a per-frame cap derived from `|sep_osc|`; re-enable the vertical dance component and delete the midline pull/recentering; widen `SPLIT_OFFSET_MAX`, shrink `RENDER_RADIUS`, rebalance the contrib formula. Source-contract tests in `qmk/QMKata/test_murmuration_source_contract.py` are updated to pin the new shape.

**Tech Stack:** C (Cortex-M4 Thumb-2, -Os, -fPIC), Python `unittest`, the existing `ModuleBuild.build_dynld` pipeline.

**Reference design:** `qmk/QMKata/docs/plans/2026-06-16-murmuration-vertical-split-speed-design.md`

---

## Task 1 — Per-frame speed cap

**Files:**
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:6` (constant)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:45-49` (clamp_speed signature)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:132-135` (after sep_osc/axis_x)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:205-206` (clamp_speed call sites)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:93` (init birds[i].vx)
- Test: `qmk/QMKata/test_murmuration_source_contract.py` (new test)

**Step 1: Write the failing test**

Append to `MurmurationSourceContractTest` in `qmk/QMKata/test_murmuration_source_contract.py`:

```python
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
        self.assertRegex(
            source,
            r"cur_max_speed_q8[^\n]*sep_osc|sep_osc[^\n]*cur_max_speed_q8",
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
```

**Step 2: Run the test to verify it fails**

Run: `python3 -m unittest qmk.QMKata.test_murmuration_source_contract.MurmurationSourceContractTest.test_max_speed_is_modulated_by_dance_phase -v`

Expected: FAIL — `'MAX_SPEED_MIN_Q8' not found in [source]`. If anything else fails first (regex syntax, import), fix the test before proceeding.

**Step 3: Apply the source change**

Edit `qmk/QMKata/dynld_animation_examples/kb_murmuration.c`.

3a. Replace the `MAX_SPEED_Q8` definition (currently line 6) with the new min/max pair:

```c
#define MAX_SPEED_MIN_Q8 80    /* slow extreme (~0.31 px/frame), at split fully open/shut */
#define MAX_SPEED_MAX_Q8 220   /* fast extreme (~0.86 px/frame), at the merge moment */
```

3b. Update `clamp_speed` to take the cap as an argument (currently at lines 45-49):

```c
static inline int16_t clamp_speed(int16_t v, int16_t cap) {
    if (v >  cap) return  cap;
    if (v < -cap) return -cap;
    return v;
}
```

3c. Update the velocity seed inside the init block (currently `birds[i].vx = CRUISE_Q8;` at line 93). No change to that line — `CRUISE_Q8 = 64` is already inside `[MAX_SPEED_MIN_Q8, MAX_SPEED_MAX_Q8]`.

3d. After the existing `int16_t sep_osc = tri8(ph);` block (currently lines 132-135), add the per-frame cap derivation:

```c
    /* Speed cap breathes with the dance: |sep_osc| is ~128 at the
     * split extremes and 0 at the merge crossing. Invert it so the cap
     * is highest when the flocks meet and lowest while fully separated. */
    int16_t abs_sep = sep_osc >= 0 ? sep_osc : (int16_t)-sep_osc;
    uint8_t merge_phase = (uint8_t)(128 - abs_sep);
    int16_t cur_max_speed_q8 = (int16_t)(MAX_SPEED_MIN_Q8 +
        (((uint32_t)merge_phase *
          (MAX_SPEED_MAX_Q8 - MAX_SPEED_MIN_Q8)) >> 7));
```

3e. Update both `clamp_speed` call sites (currently at lines 205-206):

```c
        b->vx = clamp_speed(b->vx + ax, cur_max_speed_q8);
        b->vy = clamp_speed(b->vy + ay, cur_max_speed_q8);
```

**Step 4: Run the test to verify it passes**

Run: `python3 -m unittest qmk.QMKata.test_murmuration_source_contract -v`

Expected: 12 tests, all PASS (one of the original 12 will be removed in Task 2; for now all should still pass except the soon-to-be-deleted vertical test).

**Step 5: Verify the binary still fits**

Run:

```bash
python3 - <<'PY'
import sys
sys.path.append('/home/user/qmk/qmk-tools/qmk/QMKata')
from GccToolchain import GccToolchain
from ModuleBuild import ModuleBuild, DYNLD_FUNC_SIZE
from keyboards.KeychronQ3Max import KeychronQ3Max
fw='/home/user/qmk/keychron_qmk_firmware'
src='/home/user/qmk/qmk-tools/qmk/QMKata/dynld_animation_examples/kb_murmuration.c'
includes=[
    '/tmp/opencode/murmuration-include/',
    fw + '/quantum/rgb_matrix/animations/',
    fw + '/quantum/rgb_matrix/',
    fw + '/quantum/',
    fw + '/platforms/',
    fw + '/keyboards/keychron/q3_max/',
]
toolchain=GccToolchain(KeychronQ3Max.TOOLCHAIN, firmware_path=fw)
builder=ModuleBuild(toolchain, firmware_path=fw, extra_includes=includes)
result=builder.build_dynld(src)
print('cap', DYNLD_FUNC_SIZE, 'binary', None if result is None else len(result), 'err', builder.last_error)
PY
```

Expected: `binary <some_number_below_2048> err None`. If it's None with an error, stop and report.

**Step 6: Commit**

```bash
git add qmk/QMKata/dynld_animation_examples/kb_murmuration.c \
        qmk/QMKata/test_murmuration_source_contract.py
git commit -m "feat(rgb): breathe murmuration top speed with dance phase

Replace the static MAX_SPEED_Q8=150 cap with a per-frame
cur_max_speed_q8 derived from |sep_osc|, so the flock visibly
accelerates through the merge moment and slows at the split
extremes. Range is 80..220 in Q8 (~0.31..0.86 px/frame).
clamp_speed takes the cap as an argument."
```

---

## Task 2 — Full-panel-height vertical motion

**Files:**
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:26` (VERTICAL_OFFSET_MAX)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:28` (drop MIDLINE_RECENTER_SHIFT)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:57-58` (re-add clamp_vertical_offset)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:131-139` (re-add axis_y + off_y)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:193-194` (drop mid_y pull)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:210` (drop next_y recenter)
- Test: `qmk/QMKata/test_murmuration_source_contract.py` (replace one test)

**Step 1: Replace the test**

In `qmk/QMKata/test_murmuration_source_contract.py`, find `test_vertical_motion_stays_inside_six_row_matrix` and replace its body with the new contract:

```python
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
```

**Step 2: Run the test to verify it fails**

Run: `python3 -m unittest qmk.QMKata.test_murmuration_source_contract.MurmurationSourceContractTest.test_vertical_motion_uses_full_panel_height -v`

Expected: FAIL — `vertical_offset >= 12` fails because the current value is 0.

**Step 3: Apply the source change**

3a. Bump `VERTICAL_OFFSET_MAX` (currently line 26):

```c
#define VERTICAL_OFFSET_MAX 16  /* px; half of the matrix half-height */
```

3b. Delete the `MIDLINE_RECENTER_SHIFT` line (currently line 28). The whole `#define MIDLINE_RECENTER_SHIFT 3` line goes.

3c. Re-add `clamp_vertical_offset` (currently a comment at lines 57-58). Replace the comment with:

```c
static inline int16_t clamp_vertical_offset(int16_t v) {
    if (v >  VERTICAL_OFFSET_MAX) return  VERTICAL_OFFSET_MAX;
    if (v < -VERTICAL_OFFSET_MAX) return -VERTICAL_OFFSET_MAX;
    return v;
}
```

3d. Re-add the `axis_y` local and the `off_y` derivation. Find the block (currently lines 131-139):

```c
    int16_t sep_osc = tri8(ph);
    int16_t axis_x  = tri8(aph);
    int16_t split = sep_osc > 0 ? sep_osc : 0;
    int16_t off_x = clamp_offset((int16_t)((split * axis_x) >> SPLIT_OFFSET_SHIFT));
    /* Vertical split is disabled (VERTICAL_OFFSET_MAX == 0) to keep the
     * flock visible on all six rows; re-introduce a tri8(aph + 64) axis
     * and clamp here if you raise that limit. */
    int16_t off_y = 0;
```

Replace with:

```c
    int16_t sep_osc = tri8(ph);
    int16_t axis_x  = tri8(aph);
    int16_t axis_y  = tri8((uint8_t)(aph + 64));
    int16_t split = sep_osc > 0 ? sep_osc : 0;
    int16_t off_x = clamp_offset((int16_t)((split * axis_x) >> SPLIT_OFFSET_SHIFT));
    int16_t off_y = clamp_vertical_offset((int16_t)((split * axis_y) >> SPLIT_OFFSET_SHIFT));
```

3e. Drop the `(mid_y - byp) >> 2` term inside the `ay` expression (currently around lines 193-194). Change:

```c
        int16_t ay = (int16_t)(sep_y << 3) + (ali_y >> 2) + (coh_y >> 3) +
                     ((-b->vy) >> 4) + ((mid_y - byp) >> 2) + dance_ay;
```

to:

```c
        int16_t ay = (int16_t)(sep_y << 3) + (ali_y >> 2) + (coh_y >> 3) +
                     ((-b->vy) >> 4) + dance_ay;
```

3f. Drop the `next_y` recentering (currently line 210). Delete the line:

```c
        next_y += (((int32_t)mid_y << 8) - next_y) >> MIDLINE_RECENTER_SHIFT;
```

Leave `int32_t next_y = (int32_t)b->y + b->vy;` untouched.

**Step 4: Run all tests to verify pass**

Run: `python3 -m unittest qmk.QMKata.test_murmuration_source_contract -v`

Expected: All 12 tests pass (the old vertical test is gone; the new vertical test passes; the speed test from Task 1 still passes; the other 10 are unchanged).

**Step 5: Verify the binary still fits**

Re-run the build snippet from Task 1 Step 5.

Expected: binary below 2048, err None. The change drops two ops (recenter line, mid_y pull) and adds two (axis_y, clamp_vertical_offset call), so it should roughly break even.

**Step 6: Commit**

```bash
git add qmk/QMKata/dynld_animation_examples/kb_murmuration.c \
        qmk/QMKata/test_murmuration_source_contract.py
git commit -m "feat(rgb): let murmuration use full panel height

Drop the >>3 next_y recentering and the (mid_y - byp) >> 2 pull
that snapped birds back to the centre row. Re-enable the dance's
vertical component with VERTICAL_OFFSET_MAX=16 so the two
sub-flocks can swing up and down. Edge forces + position clamps
still keep birds inside the matrix."
```

---

## Task 3 — Visibly separated sub-flocks

**Files:**
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:25` (SPLIT_OFFSET_MAX)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:18` (RENDER_RADIUS)
- Modify: `qmk/QMKata/dynld_animation_examples/kb_murmuration.c:253` (contrib formula)
- Test: `qmk/QMKata/test_murmuration_source_contract.py` (new test)

**Step 1: Write the failing test**

Append to `MurmurationSourceContractTest` in `qmk/QMKata/test_murmuration_source_contract.py`:

```python
    def test_split_clouds_are_visibly_separated(self):
        source = MURMURATION_SOURCE.read_text()

        # Wider split + smaller render kernel so the two sub-flocks
        # don't blur into one Gaussian smear.
        split = int(re.search(r"#define SPLIT_OFFSET_MAX (\d+)", source).group(1))
        render = int(re.search(r"#define RENDER_RADIUS (\d+)", source).group(1))
        self.assertGreaterEqual(split, 48,
                                "split offset too small to be visible across the kernel")
        self.assertLessEqual(render, 14,
                             "render kernel too wide to show the gap between clouds")
```

**Step 2: Run the test to verify it fails**

Run: `python3 -m unittest qmk.QMKata.test_murmuration_source_contract.MurmurationSourceContractTest.test_split_clouds_are_visibly_separated -v`

Expected: FAIL — `split >= 48` fails (current value is 32).

**Step 3: Apply the source change**

3a. Bump `SPLIT_OFFSET_MAX` (currently line 25):

```c
#define SPLIT_OFFSET_MAX 56    /* px; caps how far the flocks separate */
```

3b. Shrink `RENDER_RADIUS` (currently line 18):

```c
#define RENDER_RADIUS 12
```

`RENDER_RADIUS_SQ` is derived from `RENDER_RADIUS` on the next line, so no change there.

3c. Rebalance the contrib formula inside the render loop (currently line 253):

```c
                int16_t contrib = (int16_t)(72 - (dist_sq >> 2));
```

Change to:

```c
                int16_t contrib = (int16_t)(50 - (dist_sq >> 3));
```

Peak is now 50 at the centre of a bird, falling to ~32 at the edge of `RENDER_RADIUS_SQ = 144`. With 24 birds the sum still routinely exceeds `MAX_DENSITY = 220` near a cluster, which the existing `if (density > MAX_DENSITY) density = MAX_DENSITY;` line clamps.

**Step 4: Run all tests to verify pass**

Run: `python3 -m unittest qmk.QMKata.test_murmuration_source_contract -v`

Expected: 13 tests, all PASS.

**Step 5: Verify the binary still fits**

Re-run the build snippet from Task 1 Step 5.

Expected: binary below 2048, err None. This task only changes constants and one literal, so size delta should be ~0.

**Step 6: Commit**

```bash
git add qmk/QMKata/dynld_animation_examples/kb_murmuration.c \
        qmk/QMKata/test_murmuration_source_contract.py
git commit -m "feat(rgb): make murmuration two-cloud split visible

Widen the dance offset cap (SPLIT_OFFSET_MAX 32->56) and shrink
the per-bird render kernel (RENDER_RADIUS 18->12) so the two
sub-flocks are visibly distinct instead of blurring into one
smear. Rebalance the contrib formula (50 - (dist_sq >> 3)) so
the smaller kernel still produces usable brightness within the
existing MAX_DENSITY cap."
```

---

## Task 4 — Final verification

**Step 1: Run the whole source-contract suite**

Run: `python3 -m unittest qmk.QMKata.test_murmuration_source_contract -v`

Expected: 13 tests, all OK.

**Step 2: Final size report**

Re-run the build snippet from Task 1 Step 5. Report the binary size and the headroom (`2048 - size`).

**Step 3: Push**

```bash
git log --oneline -5
git push
```

Expected: three new commits since the last push (`feat(rgb): breathe ...`, `feat(rgb): let ... full panel height`, `feat(rgb): two-cloud split visible`). Push succeeds.

**Step 4: Hardware check** _(human)_

Load the new dynld binary onto the keyboard and confirm visually:
- Flock visibly uses rows other than just row 3.
- Two distinct cloud blobs are visible during the split extreme.
- The flock noticeably accelerates and decelerates over the dance cycle.

Report back if any of the three look wrong; iterations are local-only and don't require a firmware rebuild.
