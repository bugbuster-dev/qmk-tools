/* combos_def.h — sticky combo definitions for this module.
 *
 * Edit this file and rebuild the module to change which combos are
 * active. The firmware-side keymap is not consulted; sticky combos in
 * a module are self-contained.
 *
 * Each entry:
 *   { key1, key2, combo_action, tap_action_1, tap_action_2 }
 *
 * key1 + key2: pressed simultaneously within ~50ms to fire combo_action
 *              (KC_NO for silent arm).
 * Then: release one, keep the other held, tap the released key
 *       repeatedly to fire tap_action_N.
 *       (tap_action_1 = released key was key1, tap_action_2 = key2.)
 *
 * Keycodes use raw uint16_t values matching QMK basic keycodes. Avoid
 * QMK-specific encodings (LCTL(KC_C), etc.) here — those require
 * additional keycode-processing logic the firmware applies through
 * tap_code16; this module passes uint16_t straight through, so for
 * complex chords you should resolve them to a single keycode in your
 * keymap layout and use that instead.
 */
#pragma once

#include <stdint.h>

#ifndef KC_NO
#define KC_NO    0x0000
#endif
#ifndef KC_J
#define KC_J     0x000D
#endif
#ifndef KC_K
#define KC_K     0x000E
#endif
#ifndef KC_UP
#define KC_UP    0x0052
#endif
#ifndef KC_DOWN
#define KC_DOWN  0x0051
#endif

typedef struct {
    uint16_t key1;
    uint16_t key2;
    uint16_t combo_action;
    uint16_t tap_action_1;
    uint16_t tap_action_2;
} sticky_combo_def_t;

/* Edit these definitions and rebuild. */
static const sticky_combo_def_t module_sticky_combos[] = {
    /* Demo: J+K arms; J-held + tap K = Down; K-held + tap J = Up. */
    { KC_J, KC_K, KC_NO, KC_UP, KC_DOWN },
};

#define MODULE_STICKY_COMBO_COUNT \
    (sizeof(module_sticky_combos) / sizeof(module_sticky_combos[0]))
