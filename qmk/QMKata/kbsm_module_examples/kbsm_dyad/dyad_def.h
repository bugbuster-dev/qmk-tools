/* dyad_def.h — dyad definitions for this module.
 *
 * Edit this file and rebuild the module to change which dyads are
 * active. The firmware-side keymap is not consulted; dyad pairs in
 * a module are self-contained.
 *
 * Each entry:
 *   { primary, secondary, output }
 *
 * primary:   key held down
 * secondary: key tapped while primary is held
 * output:    keycode emitted via tap_code16 when (primary, secondary)
 *            matches
 *
 * Multiple secondaries can share a primary. A primary with no matching
 * secondary in the table behaves like a normal keystroke (tap or hold).
 *
 * Keycodes are raw uint16_t values matching QMK basic keycodes plus
 * common QMK keycode macros. tap_code16() in the firmware env handles
 * modifier-bearing values like LCTL(KC_C), so those work as outputs.
 */
#pragma once

#include <stdint.h>

#ifndef KC_NO
#define KC_NO    0x0000
#endif

/* Letter keys */
#ifndef KC_A
#define KC_A     0x0004
#endif
#ifndef KC_C
#define KC_C     0x0006
#endif
#ifndef KC_J
#define KC_J     0x000D
#endif
#ifndef KC_K
#define KC_K     0x000E
#endif
#ifndef KC_V
#define KC_V     0x0019
#endif
#ifndef KC_X
#define KC_X     0x001B
#endif
#ifndef KC_Z
#define KC_Z     0x001D
#endif

/* Punctuation / special */
#ifndef KC_ESC
#define KC_ESC   0x0029
#endif
#ifndef KC_SCLN
#define KC_SCLN  0x0033
#endif

/* QMK modifier-tap macros: LCTL(kc) = 0x0100 | kc (basic keycodes only) */
#ifndef LCTL
#define LCTL(kc) (0x0100 | (kc))
#endif

typedef struct {
    uint16_t primary;
    uint16_t secondary;
    uint16_t output;
} dyad_def_t;

/* Edit these definitions and rebuild.
 *
 * Demo configuration:
 *   ; + A → Ctrl+A (select all)
 *   ; + C → Ctrl+C (copy)
 *   ; + V → Ctrl+V (paste)
 *   ; + X → Ctrl+X (cut)
 *   ; + Z → Ctrl+Z (undo)
 *   J + K → Escape (Vim escape mnemonic)
 *
 * Each dyad consumes both the primary press and the secondary tap;
 * holding ; alone (and releasing) still types a semicolon normally.
 */
static const dyad_def_t module_dyads[] = {
    { KC_SCLN, KC_A, LCTL(KC_A) },
    { KC_SCLN, KC_C, LCTL(KC_C) },
    { KC_SCLN, KC_V, LCTL(KC_V) },
    { KC_SCLN, KC_X, LCTL(KC_X) },
    { KC_SCLN, KC_Z, LCTL(KC_Z) },
    { KC_J,    KC_K, KC_ESC     },
};

#define MODULE_DYAD_COUNT \
    (sizeof(module_dyads) / sizeof(module_dyads[0]))
