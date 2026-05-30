# kbsm_holdseq — SRAM-loaded hold sequence module

Hold a primary key, tap a variable-length sequence of secondary keys, release primary — lookup `(primary, sequence)` in config table, fire expansion via send_string. On no-match, replay all consumed keys as normal taps.

## What it does

Hold `;` + tap `g`, `o` → fires `"git checkout -b "`. Hold `;` alone → release → types `;` normally. The primary key is both the macro activator and a normal key.

Default config:
| Hold | Sequence | Expansion |
|---|---|---|
| `;` | `go` | `git checkout -b ` |
| `;` | `pr` | `git pull --rebase ` |
| `;` | `co` | `git checkout ` |
| `;` | `cm` | `git commit -m ""` |
| `j` | `k` | `jump` |

## Files

| File | Purpose |
|---|---|
| `holdseq.puml` | StateSmith diagram (3 states, 5 events) |
| `Holdseq.{c,h}` | Generated SM (committed; regen via StateSmith CLI) |
| `holdseq_def.h` | User-editable config + keycode→char lookup |
| `holdseq_module.c` | Adapter (env-routed) |
| `README.md` | This file |

## State machine

```
IDLE → primary press → PRIMARY_HELD
                          ├─ tap → COLLECTING
                          │         ├─ more taps → COLLECTING
                          │         ├─ release → fire or replay
                          │         └─ non-printable → break + replay
                          ├─ release alone → normal tap
                          └─ non-printable → commit as hold
```

## Build & upload

```bash
python3 emulator/scripts/build_sram_module.py --feature holdseq
```

Produces `.build/kbsm_holdseq.bin` (relocated for slot 8) and
`.build/kbsm_holdseq.json` (slot metadata).

## Regenerating the SM

```bash
~/.local/bin/statesmith run --lang C99 --no-csx --no-ask \
    qmk-tools/qmk/QMKata/kbsm_module_examples/kbsm_holdseq/holdseq.puml
```

## Known limitations (v1)

- QWERTY layout only (keycode-to-ASCII table is QWERTY-specific)
- ASCII only; no Unicode support
- Single primary at a time
- Replay on no-match uses `tap_code16` (bypasses kbsm chain — documented limitation)
- Compile-time const config only (no EEPROM/QMKata runtime editing)

See `keychron_qmk_firmware/docs/plans/2026-05-24-holdseq-design.md` for full
design rationale.
