# kbsm_vim_modal — SRAM-loaded vim modal layer

5-mode vim-style modal editor for QMK keyboards. Ported from the
firmware-side `quantum/features/vim_modal_adapter.c`.

## Modes

| Mode | Behavior | Entry keys |
|---|---|---|
| **Normal** | hjkl→arrows, i/a/o→insert, v→visual, commands | Default on load |
| **Insert** | Pass all keys through; Esc→Normal | `i`, `a`, `o` |
| **Visual** | Shift+arrows for selection; y→copy, d→cut | `v` |
| **Command** | Stub — Esc→Normal, Enter→Normal | `:` (not wired in v1) |
| **Replace** | Each keystroke replaces char (Del + key) | `R` (not wired in v1) |

## Normal mode key bindings

| Key | Action |
|---|---|
| `h`/`j`/`k`/`l` | Left/Down/Up/Right |
| `w`/`b` | Word forward/back (Ctrl+Right/Left) |
| `0` | Home |
| `.` | End |
| `g` | Top of file (Ctrl+Home) |
| `x` | Delete |
| `u` | Undo (Ctrl+Z) |
| `r` | Redo (Ctrl+Y, mapped to 'r' for demo) |
| `p` | Paste (Ctrl+V) |
| `y` | Yank/copy (Ctrl+C) |
| `i` | Insert mode |
| `a` | Insert after cursor (Right + Insert) |
| `o` | Open line below (End + Enter + Insert) |

All other keys suppressed in Normal mode.

Always active when loaded. Unload the module to disable vim mode.

## Files

| File | Purpose |
|---|---|
| `vim_modal.puml` | StateSmith diagram (5 states, 8 events) |
| `VimModal.{c,h}` | Generated SM (committed; regen via StateSmith CLI) |
| `vim_modal_def.h` | Keycode definitions + config |
| `vim_modal_module.c` | Adapter (env-routed) |
| `README.md` | This file |

## State machine

```
NORMAL ──i/a/o──→ INSERT ──Esc──→ NORMAL
NORMAL ──v──────→ VISUAL ──Esc──→ NORMAL
NORMAL ──:──────→ COMMAND ──Esc/Enter→ NORMAL
NORMAL ──R──────→ REPLACE ──Esc──→ NORMAL
```

## Build & upload

```bash
python3 emulator/scripts/build_sram_module.py --feature vim_modal
```

## Regenerating the SM

```bash
~/.local/bin/statesmith run --lang C99 --no-csx --no-ask \
    qmk-tools/qmk/QMKata/kbsm_module_examples/kbsm_vim_modal/vim_modal.puml
```
