/* autotext_def.h — autotext trigger table and keycode-to-ASCII lookup.
 *
 * Edit the trigger table and rebuild the module to change which
 * abbreviations are expanded. The firmware-side keymap is not consulted;
 * autotext triggers in a module are self-contained.
 *
 * Each entry:
 *   { trigger, expansion }
 *
 * trigger:   the character sequence to match (null-terminated ASCII)
 * expansion: the string to send via SEND_STRING (null-terminated ASCII)
 *
 * Triggers fire on exact match. The typed trigger characters reach the
 * host normally as the user types; when a full match is detected, the
 * module sends backspaces to delete the trigger, then sends the expansion.
 *
 * Conventions:
 * - Triggers should not be prefixes of each other (e.g., "te" and "teh").
 *   The first exact match wins; the longer trigger never fires.
 * - Triggers are case-sensitive in v1. "TEH" is not "teh".
 * - Only ASCII printable characters are matched. Non-printable keys
 *   (arrows, function keys, modifiers alone) break any partial match.
 * - QWERTY layout assumed for the keycode-to-ASCII lookup table.
 *   Users on non-QWERTY layouts should provide their own table.
 */
#pragma once

#include <stdint.h>

#ifndef KC_NO
#define KC_NO    0x0000
#endif

/* QMK basic keycodes (QWERTY layout).
 * These are the raw uint16_t values matching QMK's basic keycodes.
 * The module uses these to convert key events to printable characters
 * for trigger matching.
 */
#ifndef KC_A
#define KC_A     0x0004
#endif
#ifndef KC_B
#define KC_B     0x0005
#endif
#ifndef KC_C
#define KC_C     0x0006
#endif
#ifndef KC_D
#define KC_D     0x0007
#endif
#ifndef KC_E
#define KC_E     0x0008
#endif
#ifndef KC_F
#define KC_F     0x0009
#endif
#ifndef KC_G
#define KC_G     0x000A
#endif
#ifndef KC_H
#define KC_H     0x000B
#endif
#ifndef KC_I
#define KC_I     0x000C
#endif
#ifndef KC_J
#define KC_J     0x000D
#endif
#ifndef KC_K
#define KC_K     0x000E
#endif
#ifndef KC_L
#define KC_L     0x000F
#endif
#ifndef KC_M
#define KC_M     0x0010
#endif
#ifndef KC_N
#define KC_N     0x0011
#endif
#ifndef KC_O
#define KC_O     0x0012
#endif
#ifndef KC_P
#define KC_P     0x0013
#endif
#ifndef KC_Q
#define KC_Q     0x0014
#endif
#ifndef KC_R
#define KC_R     0x0015
#endif
#ifndef KC_S
#define KC_S     0x0016
#endif
#ifndef KC_T
#define KC_T     0x0017
#endif
#ifndef KC_U
#define KC_U     0x0018
#endif
#ifndef KC_V
#define KC_V     0x0019
#endif
#ifndef KC_W
#define KC_W     0x001A
#endif
#ifndef KC_X
#define KC_X     0x001B
#endif
#ifndef KC_Y
#define KC_Y     0x001C
#endif
#ifndef KC_Z
#define KC_Z     0x001D
#endif
#ifndef KC_1
#define KC_1     0x001E
#endif
#ifndef KC_2
#define KC_2     0x001F
#endif
#ifndef KC_3
#define KC_3     0x0020
#endif
#ifndef KC_4
#define KC_4     0x0021
#endif
#ifndef KC_5
#define KC_5     0x0022
#endif
#ifndef KC_6
#define KC_6     0x0023
#endif
#ifndef KC_7
#define KC_7     0x0024
#endif
#ifndef KC_8
#define KC_8     0x0025
#endif
#ifndef KC_9
#define KC_9     0x0026
#endif
#ifndef KC_0
#define KC_0     0x0027
#endif
#ifndef KC_SPACE
#define KC_SPACE 0x002C
#endif
#ifndef KC_ENTER
#define KC_ENTER 0x0028
#endif
#ifndef KC_ESC
#define KC_ESC   0x0029
#endif
#ifndef KC_TAB
#define KC_TAB   0x002B
#endif
#ifndef KC_BSPC
#define KC_BSPC  0x002A
#endif
#ifndef KC_DEL
#define KC_DEL   0x004C
#endif
#ifndef KC_BSLS
#define KC_BSLS  0x0031
#endif
#ifndef KC_QUOT
#define KC_QUOT  0x0032
#endif
#ifndef KC_SCLN
#define KC_SCLN  0x0033
#endif
#ifndef KC_COMM
#define KC_COMM  0x0036
#endif
#ifndef KC_DOT
#define KC_DOT   0x0037
#endif
#ifndef KC_SLSH
#define KC_SLSH  0x0038
#endif
#ifndef KC_MINUS
#define KC_MINUS 0x0039
#endif
#ifndef KC_EQL
#define KC_EQL   0x003A
#endif
#ifndef KC_LBRC
#define KC_LBRC  0x003B
#endif
#ifndef KC_RBRC
#define KC_RBRC  0x003C
#endif

/* Maximum trigger length. Triggers longer than this are ignored. */
#define AUTOTEXT_MAX_TRIGGER_LEN 16

typedef struct {
    const char *trigger;
    const char *expansion;
} autotext_def_t;

/* Edit these definitions and rebuild.
 *
 * Demo configuration:
 *   "teh" → "the" (typo fix)
 *   "/email" → "alice@example.com" (email address)
 *   "btw" → "by the way " (common abbreviation)
 *   "idk" → "I don't know" (common abbreviation)
 *   "brb" → "be right back" (common abbreviation)
 *
 * Each trigger fires on exact match. The typed trigger characters
 * reach the host normally; when a full match is detected, the module
 * sends backspaces to delete the trigger, then sends the expansion.
 */
static const autotext_def_t module_autotext[] = {
    { "teh",    "the" },
    { "/email", "alice@example.com" },
    { "btw",    "by the way " },
    { "idk",    "I don't know" },
    { "brb",    "be right back" },
};

#define MODULE_AUTOTEXT_COUNT \
    (sizeof(module_autotext) / sizeof(module_autotext[0]))

/* Keycode-to-ASCII lookup table for QWERTY layout.
 *
 * Users on non-QWERTY layouts (Dvorak, AZERTY, Colemak, etc.) should
 * provide their own table. The module uses this to convert key events
 * to printable characters for trigger matching.
 *
 * Format: { keycode, character }
 * Sentinel: { 0, 0 } marks the end of the table.
 *
 * Shift-modified characters (uppercase letters, shifted punctuation)
 * are not handled in v1 (no get_mods() in kbsm_env_t).
 */
typedef struct { uint16_t kc; char ch; } keycode_char_t;

static const keycode_char_t keycode_to_char[] = {
    /* Lowercase letters */
    { KC_A, 'a' }, { KC_B, 'b' }, { KC_C, 'c' }, { KC_D, 'd' },
    { KC_E, 'e' }, { KC_F, 'f' }, { KC_G, 'g' }, { KC_H, 'h' },
    { KC_I, 'i' }, { KC_J, 'j' }, { KC_K, 'k' }, { KC_L, 'l' },
    { KC_M, 'm' }, { KC_N, 'n' }, { KC_O, 'o' }, { KC_P, 'p' },
    { KC_Q, 'q' }, { KC_R, 'r' }, { KC_S, 's' }, { KC_T, 't' },
    { KC_U, 'u' }, { KC_V, 'v' }, { KC_W, 'w' }, { KC_X, 'x' },
    { KC_Y, 'y' }, { KC_Z, 'z' },
    /* Digits */
    { KC_1, '1' }, { KC_2, '2' }, { KC_3, '3' }, { KC_4, '4' },
    { KC_5, '5' }, { KC_6, '6' }, { KC_7, '7' }, { KC_8, '8' },
    { KC_9, '9' }, { KC_0, '0' },
    /* Punctuation / special */
    { KC_SPACE, ' ' },
    { KC_ENTER, '\n' },
    { KC_TAB, '\t' },
    { KC_BSPC, '\b' },
    { KC_DEL, '\x7f' },
    { KC_BSLS, '\\' },
    { KC_QUOT, '\'' },
    { KC_SCLN, ';' },
    { KC_COMM, ',' },
    { KC_DOT, '.' },
    { KC_SLSH, '/' },
    { KC_MINUS, '-' },
    { KC_EQL, '=' },
    { KC_LBRC, '[' },
    { KC_RBRC, ']' },
    { 0, 0 } /* sentinel */
};
