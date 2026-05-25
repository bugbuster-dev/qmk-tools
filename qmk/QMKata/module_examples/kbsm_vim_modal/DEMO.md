# vim_modal — Demo Scenarios

Manual test procedures for validating the vim modal SRAM module.
Load the module before testing:

```bash
python3 emulator/scripts/build_sram_module.py --feature vim_modal
# Upload .build/kbsm_vim_modal.bin to slot 8 via QMKata
```

## Scenario 1 — Basic navigation (Normal mode)

**Setup:** Module loaded, vim mode active (NORMAL).

| Step | Action | Expected |
|---|---|---|
| 1 | Press `j` | Cursor moves **down** one line |
| 2 | Press `k` | Cursor moves **up** one line |
| 3 | Press `h` | Cursor moves **left** one char |
| 4 | Press `l` | Cursor moves **right** one char |
| 5 | Press `w` | Cursor jumps forward one **word** |
| 6 | Press `b` | Cursor jumps backward one **word** |
| 7 | Press `0` | Cursor jumps to line **start** |
| 8 | Press `.` | Cursor jumps to line **end** |
| 9 | Type `abcdef` in a text editor | **Nothing appears** — all keys suppressed in Normal |

## Scenario 2 — Mode transitions

| Step | Action | Expected |
|---|---|---|
| 1 | Press `i` | Enters **Insert** mode (cursor doesn't move) |
| 2 | Type `hello` | `hello` appears on the host |
| 3 | Press `Escape` | Returns to **Normal** mode |
| 4 | Type `world` | **Nothing appears** — back in Normal |

| Step | Action | Expected |
|---|---|---|
| 1 | Press `a` | Enters Insert mode **after cursor** (sends Right first) |
| 2 | Type `append` | `append` appears one char to the right |
| 3 | Press `Escape` | Returns to Normal |

| Step | Action | Expected |
|---|---|---|
| 1 | Press `o` | End, Enter, then Insert mode (new line below) |
| 2 | Type `newline` | Text appears on a new line |
| 3 | Press `Escape` | Returns to Normal |

## Scenario 3 — Visual mode (selection)

**Setup:** Open a text editor, type some text, return to NORMAL.

| Step | Action | Expected |
|---|---|---|
| 1 | Press `v` | Enters **Visual** mode |
| 2 | Press `j` | Selection extends **down** one line (Shift+Down) |
| 3 | Press `j` again | Selection extends another line |
| 4 | Press `l` | Selection extends **right** one char |
| 5 | Press `h` | Selection extends **left** one char |
| 6 | Press `y` | Selection **copied** (Ctrl+C), returns to Normal |
| 7 | Press `p` | **Pastes** copied text (Ctrl+V) |
| 8 | Press `v`, then `d` | Selection **cut** (Ctrl+X), returns to Normal |

## Scenario 4 — Edit commands (Normal mode)

| Step | Action | Expected |
|---|---|---|
| 1 | Press `x` | Deletes character under cursor |
| 2 | Press `u` | Undo (Ctrl+Z) |
| 3 | Press `r` | Redo (Ctrl+Y) |
| 4 | Press `p` | Paste (Ctrl+V) |
| 5 | Press `y` | Copy (Ctrl+C) — note: in vim this is yank, here it's host copy |

## Scenario 5 — Escape always returns to Normal

| Step | Action | Expected |
|---|---|---|
| 1 | Press `i`, type `test`, press `Escape` | Returns to Normal |
| 2 | Press `v`, press `j`, `j`, press `Escape` | Returns to Normal |
| 3 | Press `o`, type `test`, press `Escape` | Returns to Normal |

Pressing Escape in Normal mode has no effect (key consumed, no output).

## Scenario 6 — Unload to disable vim mode

| Step | Action | Expected |
|---|---|---|
| 1 | Module loaded — type `abc` | **Nothing** (Normal mode suppresses keys) |
| 2 | Unload module via QMKata | Module deinitialized |
| 3 | Type `abc` | `abc` appears normally |
| 4 | Reload module | Vim mode active again |

## Scenario 7 — Priority check (runs before dyad)

**Setup:** Load both vim_modal (slot 8) and dyad (slots conflict — only one SRAM slot by default).

**Note:** Only one module can be in the 4 KB SRAM slot at a time. To test priority ordering, build vim_modal into firmware (`VIM_MODAL_ENABLE = yes`) with dyad loaded in SRAM. Vim_modal priority 50 runs before dyad priority 60 — so vim_modal intercepts J/K before dyad can fire its `;+J` or `;+K` dyads.

| Step | Action | Expected |
|---|---|---|
| 1 | Press `j` in Normal mode | Cursor moves down (vim_modal consumed it) |
| 2 | Dyad `;` held + tap `j` | `;` is consumed by vim_modal (all keys suppressed in Normal) — dyad never fires |

## Scenario 8 — Replace mode

| Step | Action | Expected |
|---|---|---|
| 1 | Enter Replace mode (requires `R` key mapped to enter Replace — not wired in default v1) | Replace mode |
| 2 | Type a character | Delete + that character passes through |
| 3 | Press Escape | Returns to Normal |
