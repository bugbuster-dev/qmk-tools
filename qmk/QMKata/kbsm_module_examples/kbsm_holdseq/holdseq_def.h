/* holdseq_def.h — hold sequence (holdseq) definitions for this module.
 *
 * Edit this file and rebuild to change which hold-sequences are active.
 *
 * Each entry: { primary, sequence, expansion }
 * - primary:    single character (QWERTY lookup, lowercase letters)
 * - sequence:   secondary key sequence (null-terminated, max HOLDSEQ_MAX_SEQ_LEN chars)
 * - expansion:  send_string output when (primary, sequence) matches
 *
 * Inline char arrays (not pointers) — string data lives inside the struct
 * so it's copied to SRAM with the module (GCC doesn't emit R_ARM_ABS32
 * relocations for .rodata→.rodata pointer references in SRAM builds).
 */
#pragma once

#include <stdint.h>

#define HOLDSEQ_MAX_SEQ_LEN  8
#define HOLDSEQ_MAX_EXP_LEN 32

typedef struct {
    char primary;
    char sequence[HOLDSEQ_MAX_SEQ_LEN];
    char expansion[HOLDSEQ_MAX_EXP_LEN];
} holdseq_def_t;

/* Edit these definitions and rebuild. */
static const holdseq_def_t module_holds[] = {
    { ';', "cb",  "git checkout -b " },
    { ';', "pr",  "git pull --rebase " },
    { ';', "p",   "git pull " },
    { ';', "co",  "git checkout " },
    { ';', "cm",  "git commit -m \"\"" },
};
#define MODULE_HOLDSEQ_COUNT (sizeof(module_holds) / sizeof(module_holds[0]))

/* QMK basic keycodes for keycode-to-ASCII lookup (QWERTY). */
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
#ifndef KC_SPACE
#define KC_SPACE 0x002C
#endif
#ifndef KC_SLSH
#define KC_SLSH  0x0038
#endif
#ifndef KC_DOT
#define KC_DOT   0x0037
#endif
#ifndef KC_MINUS
#define KC_MINUS 0x0039
#endif
#ifndef KC_COMM
#define KC_COMM  0x0036
#endif
#ifndef KC_SCLN
#define KC_SCLN  0x0033
#endif
#ifndef KC_ENTER
#define KC_ENTER 0x0028
#endif
#ifndef KC_TAB
#define KC_TAB   0x002B
#endif
#ifndef KC_BSPC
#define KC_BSPC  0x002A
#endif
#ifndef KC_ESC
#define KC_ESC   0x0029
#endif

typedef struct { uint16_t kc; char ch; } keycode_char_t;

static const keycode_char_t keycode_to_char[] = {
    { KC_A,'a' }, { KC_B,'b' }, { KC_C,'c' }, { KC_D,'d' },
    { KC_E,'e' }, { KC_F,'f' }, { KC_G,'g' }, { KC_H,'h' },
    { KC_I,'i' }, { KC_J,'j' }, { KC_K,'k' }, { KC_L,'l' },
    { KC_M,'m' }, { KC_N,'n' }, { KC_O,'o' }, { KC_P,'p' },
    { KC_Q,'q' }, { KC_R,'r' }, { KC_S,'s' }, { KC_T,'t' },
    { KC_U,'u' }, { KC_V,'v' }, { KC_W,'w' }, { KC_X,'x' },
    { KC_Y,'y' }, { KC_Z,'z' },
    { KC_SPACE, ' ' }, { KC_SLSH, '/' }, { KC_DOT, '.' },
    { KC_MINUS, '-' }, { KC_COMM, ',' }, { KC_SCLN, ';' },
    { KC_ENTER, '\n' }, { KC_TAB, '\t' }, { KC_BSPC, '\b' },
    { 0, 0 }
};
