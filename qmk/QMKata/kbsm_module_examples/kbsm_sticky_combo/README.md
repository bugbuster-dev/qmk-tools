# kbsm_sticky_combo — SRAM-loaded sticky combo module

Demonstrates the SRAM module path with a feature that benefits from
the kbsm: sticky combos.

## What it does

Identical to the firmware-built `STICKY_COMBO_ENABLE` feature in
`quantum/features/sticky_combo_adapter.c`, but loadable into SRAM
at runtime — no firmware reflash required to change behavior.

- Press `key1` + `key2` simultaneously (< 50 ms) → fires `combo_action`.
- Keep `key2` held, tap `key1` → fires `tap_action_1` per tap.
- Keep `key1` held, tap `key2` → fires `tap_action_2` per tap.
- Releasing the held key ends the sequence.

Default: `J + K` arms; J-held + tap-K = `Down`, K-held + tap-J = `Up`.

## Files

| File | Purpose |
|------|---------|
| `combos_def.h` | User-editable: sticky combo array. Edit and rebuild. |
| `sticky_combo_module.c` | Adapter (port of firmware adapter, env-routed) |
| `StickyCombo.c/.h` | StateSmith-generated 4-state machine (copied from firmware) |

## Build & upload

Requires firmware built with:
- `KEY_BEHAVIOR_SM_ENABLE = yes`
- `MODULE_SRAM_ENABLE = yes`
- (Optional) `STICKY_COMBO_ENABLE = no` so the firmware copy doesn't double-register.

From the firmware repo:

```bash
python3 emulator/scripts/build_sram_module.py --feature sticky_combo
```

Produces `.build/kbsm_sticky_combo.bin` (relocated for slot 8) and
`.build/kbsm_sticky_combo.json` (slot metadata). The helper resolves the
firmware's actual `g_module_sram` address before applying relocations and
the final CRC.

Load the resulting `.bin` into slot 8 via the QMKata host tool.

## Editing combos

Open `combos_def.h`, modify `module_sticky_combos[]`, save, rebuild,
re-upload. No firmware flash. Resets are still volatile — the module
is lost on power cycle and must be re-uploaded.

## Volatility

SRAM modules disappear on reset. This is by design — the iteration
workflow trades persistence for zero flash wear. Once a configuration
is stable, port to the firmware-side `STICKY_COMBO_ENABLE = yes` build
path so it survives reboot.
