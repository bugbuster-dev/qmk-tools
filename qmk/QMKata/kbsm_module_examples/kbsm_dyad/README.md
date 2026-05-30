# kbsm_dyad — SRAM-loaded dyad module

Demonstrates the SRAM module path with a kbsm feature that has no
firmware-built counterpart: **dyad**, a 2D (held_letter, tapped_letter) →
output keycode mapping.

## What it does

Hold a *primary* key (typically a letter or punctuation). While it's
held, tapping a *secondary* key fires an arbitrary configured output
keycode instead of the secondary's normal value. Release the primary to
exit.

- Hold `;`, tap `A` → fires `Ctrl+A` (select all)
- Hold `;`, tap `C` → fires `Ctrl+C` (copy)
- Hold `;`, tap `V` → fires `Ctrl+V` (paste)
- Hold `J`, tap `K` → fires `Esc` (Vim escape mnemonic)
- Press `;` alone (no secondary) → types `;` normally on release

Default table lives in `dyad_def.h`. Edit and rebuild.

## How it differs from existing QMK features

| Feature | Trigger | Why dyad isn't a duplicate |
|---|---|---|
| Combo | Simultaneous press of N keys | Dyad is sequential: primary first, then secondary |
| Key override | Modifier(s) + key | Dyad's "modifier" is any letter, not a modifier key |
| Tap-dance | N taps/holds of one key | Dyad involves a pair, not a single key |
| Space-cadet | One key: shift-on-hold, paren-on-tap | Space-cadet is per-key with one fixed output; dyad is per-pair with configurable output |
| kbsm sticky combo | Simultaneous press of 2 keys then arm | Dyad never requires simultaneous press; primary holds the "key" role explicitly |

## Files

| File | Purpose |
|---|---|
| `dyad.puml` | StateSmith diagram (3 states, 5 events) |
| `Dyad.{c,h}` | Generated SM (committed; regen via StateSmith CLI) |
| `dyad_def.h` | User-editable: dyad table |
| `dyad_module.c` | Adapter (env-routed) |
| `README.md` | This file |

## State machine

```
IDLE
  └─ on_primary_press ──> PRIMARY_HELD
                            ├─ on_secondary_match ──> ARMED
                            ├─ on_primary_release ──> IDLE  (was just a normal tap)
                            └─ on_other_key       ──> IDLE  (primary commits as held)

ARMED
  ├─ on_secondary_repeat ──> ARMED  (output fires again)
  └─ on_primary_release  ──> IDLE
```

Adapter holds: `held_primary` (which key), `active_dyad_index` (which row
of the table is currently armed), `primary_committed_to_host` (whether
`register_code16` has been called for a held primary that became a
normal hold). No timer state — dyad decisions are purely event-ordered.

## Build & upload

Requires firmware built with:
- `KEY_BEHAVIOR_SM_ENABLE = yes`
- `MODULE_SRAM_ENABLE = yes`

From the firmware repo:

```bash
python3 emulator/scripts/build_sram_module.py --feature dyad
```

Produces `.build/kbsm_dyad.bin` (relocated for slot 8) and
`.build/kbsm_dyad.json` (slot metadata).

The helper resolves the firmware's actual `g_module_sram` address before
applying relocations and the final CRC.

Load the resulting `.bin` into slot 8 via the QMKata host tool.

## Regenerating `Dyad.{c,h}` from the diagram

This module's `.puml` lives outside `quantum/features/`, so
`make statesmith-gen` does NOT regenerate it. Run manually:

```bash
~/.local/bin/statesmith run --lang C99 --no-csx --no-ask \
    qmk-tools/qmk/QMKata/kbsm_module_examples/kbsm_dyad/dyad.puml
```

Then apply the GCC pragma guard (see
`docs/installing-statesmith.md` in the firmware repo for the snippet).
The generated files are committed so end users don't need StateSmith
installed.

## Editing the dyad table

Open `dyad_def.h`, modify `module_dyads[]`, save, rebuild, re-upload.
No firmware reflash required. SRAM modules are lost on power cycle, so
this iteration loop is fast and flash-friendly.

## Known limitations (v1)

- **Single primary at a time.** If two primary-eligible keys are pressed
  in sequence without an intervening release, the second one is treated
  as "other key" (third-key path), not as a new candidate primary. The
  first primary commits to the host as a normal hold.
- **Rolling-typing risk.** A user typing fast through a (primary,
  secondary) pair will inadvertently fire the dyad. Avoid putting common
  letter pairs in the table. A timer guard is planned for v2.
- **Secondary release asymmetry.** When ARMED, the secondary's press
  consumed but its release passes through. Most hosts ignore unpaired
  releases; flagged for future review.
- **Output via `tap_code16` only.** Single-keycode outputs (incl.
  modifier-bearing macros like `LCTL(KC_A)`). No `SEND_STRING` support.

See `keychron_qmk_firmware/docs/plans/2026-05-24-dyad-design.md` for the
full design rationale and out-of-scope items.

## Volatility

SRAM modules disappear on reset. This is by design — the iteration
workflow trades persistence for zero flash wear. Once a dyad
configuration is stable, port it to a firmware-side feature for
persistence.
