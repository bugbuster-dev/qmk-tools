# kbsm_autotext — SRAM-loaded autotext module

Demonstrates the SRAM module path with a kbsm feature that has no
firmware-built counterpart: **autotext**, abbreviation expansion at
the firmware level.

## What it does

Watch your typing in real time. When a configured trigger sequence is
matched, the module sends backspaces to delete the trigger and sends
the configured expansion via `SEND_STRING`.

- Type `teh` → host shows `the`
- Type `/email` → host shows `alice@example.com`
- Type `btw` → host shows `by the way `
- Type `idk` → host shows `I don't know`
- Type `brb` → host shows `be right back`

Trigger characters reach the host normally until a full match is detected.
The trigger-completing character is consumed, so it never reaches the host;
the module backspaces only the already-sent prefix characters, then sends the
expansion. This avoids the final character appearing after the expansion.

## How it differs from existing QMK features

| Feature | Trigger | Why autotext isn't a duplicate |
|---|---|---|
| Dynamic macros | Record + replay on a key | Autotext fires on typed text, not a dedicated key |
| Leader | Leader key + sequence | Autotext has no leader key; fires on raw typing |
| Key override | Modifier + key | Autotext matches arbitrary character sequences |
| Tap-dance | N taps of one key | Autotext matches multi-character sequences |
| kbsm dyad | Hold primary, tap secondary | Dyad is a two-key pair; autotext is a typed sequence |

## Files

| File | Purpose |
|---|---|
| `autotext.puml` | StateSmith diagram (2 states, 4 events) |
| `Autotext.{c,h}` | Generated SM (committed; regen via StateSmith CLI) |
| `autotext_def.h` | User-editable: trigger table + keycode→ASCII lookup |
| `autotext_module.c` | Adapter (env-routed) |
| `README.md` | This file |

## State machine

```
IDLE
  └─ on_first_match_char ──> ACCUMULATING
                                ├─ on_extend_match ──> ACCUMULATING
                                ├─ on_full_match     ──> IDLE (fires expansion)
                                └─ on_break_match    ──> IDLE (buffer cleared)
```

2 states, 4 events. The SM is mostly a topology document — the real
matching logic (prefix scan, buffer management, backspace + SEND_STRING)
lives in the adapter. The SM exists to provide kbsm machinery (init/deinit/
handle/reset) and document the intent.

## Build & upload

Requires firmware built with:
- `KEY_BEHAVIOR_SM_ENABLE = yes`
- `MODULE_SRAM_ENABLE = yes`

From the firmware repo:

```bash
python3 emulator/scripts/build_sram_module.py --feature autotext
```

Produces `.build/kbsm_autotext.bin` (relocated for slot 8) and
`.build/kbsm_autotext.json` (slot metadata).

The helper resolves the firmware's actual `g_module_sram` address before
applying relocations and the final CRC.

Load the resulting `.bin` into slot 8 via the QMKata host tool.

## Regenerating `Autotext.{c,h}` from the diagram

This module's `.puml` lives outside `quantum/features/`, so
`make statesmith-gen` does NOT regenerate it. Run manually:

```bash
~/.local/bin/statesmith run --lang C99 --no-csx --no-ask \
    qmk-tools/qmk/QMKata/kbsm_module_examples/kbsm_autotext/autotext.puml
```

Then apply the GCC pragma guard (see
`docs/installing-statesmith.md` in the firmware repo for the snippet).
The generated files are committed so end users don't need StateSmith
installed.

## Editing the trigger table

Open `autotext_def.h`, modify `module_autotext[]`, save, rebuild,
re-upload. No firmware reflash required. SRAM modules are lost on
power cycle, so this iteration loop is fast and flash-friendly.

Triggers should not be prefixes of each other (e.g., "te" and "teh").
The first exact match wins; the longer trigger never fires.

## Known limitations (v1)

- **QWERTY layout only.** The keycode-to-ASCII lookup table assumes
  QWERTY. Users on Dvorak, AZERTY, Colemak, etc. need to provide
  their own table. Documented as v1 limitation.
- **Case-sensitive triggers.** "TEH" is not "teh". Shift-modified
  characters are not handled in v1 (no `get_mods()` in kbsm_env_t).
  Case-insensitive matching is deferred to v2.
- **ASCII only.** No Unicode support. Expansions are null-terminated
  ASCII strings. Unicode expansions deferred to v2.
- **Single trigger at a time.** If you type a character that starts
  multiple triggers, the first one in the table wins. Longest-match-wins
  precedence is deferred to v2.
- **Termination-character mode.** Triggers fire on exact match, not
  after a termination character (space, punctuation, enter). Users
  who want `/email ` to fire only after the space should add the
  space to the trigger: `{ "/email ", "alice@example.com" }`.
- **Backspace handling.** Backspace truncates the buffer by one. If
  the user backspaces after a trigger has fired, the module doesn't
  know the host state was rewritten. Behavior is typically fine but
  not perfect.

See `keychron_qmk_firmware/docs/plans/2026-05-24-autotext-design.md` for
the full design rationale and out-of-scope items.

## Volatility

SRAM modules disappear on reset. This is by design — the iteration
workflow trades persistence for zero flash wear. Once a trigger table
is stable, port it to a firmware-side feature for persistence.
