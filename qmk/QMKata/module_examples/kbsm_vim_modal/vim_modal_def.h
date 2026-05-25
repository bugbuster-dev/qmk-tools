/* vim_modal_def.h — keycode definitions and config for vim_modal SRAM module.
 *
 * Edit the key mappings to customize the vim modal behavior.
 */
#pragma once
#include <stdint.h>

/* ---- QMK basic keycodes ---- */
#ifndef KC_A
#define KC_A       0x0004
#endif
#ifndef KC_B
#define KC_B       0x0005
#endif
#ifndef KC_C
#define KC_C       0x0006
#endif
#ifndef KC_D
#define KC_D       0x0007
#endif
#ifndef KC_E
#define KC_E       0x0008
#endif
#ifndef KC_F
#define KC_F       0x0009
#endif
#ifndef KC_G
#define KC_G       0x000A
#endif
#ifndef KC_H
#define KC_H       0x000B
#endif
#ifndef KC_I
#define KC_I       0x000C
#endif
#ifndef KC_J
#define KC_J       0x000D
#endif
#ifndef KC_K
#define KC_K       0x000E
#endif
#ifndef KC_L
#define KC_L       0x000F
#endif
#ifndef KC_M
#define KC_M       0x0010
#endif
#ifndef KC_N
#define KC_N       0x0011
#endif
#ifndef KC_O
#define KC_O       0x0012
#endif
#ifndef KC_P
#define KC_P       0x0013
#endif
#ifndef KC_Q
#define KC_Q       0x0014
#endif
#ifndef KC_R
#define KC_R       0x0015
#endif
#ifndef KC_S
#define KC_S       0x0016
#endif
#ifndef KC_T
#define KC_T       0x0017
#endif
#ifndef KC_U
#define KC_U       0x0018
#endif
#ifndef KC_V
#define KC_V       0x0019
#endif
#ifndef KC_W
#define KC_W       0x001A
#endif
#ifndef KC_X
#define KC_X       0x001B
#endif
#ifndef KC_Y
#define KC_Y       0x001C
#endif
#ifndef KC_Z
#define KC_Z       0x001D
#endif
#ifndef KC_0
#define KC_0       0x0027
#endif
#ifndef KC_DOT
#define KC_DOT     0x0037
#endif
#ifndef KC_ENTER
#define KC_ENTER   0x0028
#endif
#ifndef KC_ESC
#define KC_ESC     0x0029
#endif
#ifndef KC_BSPC
#define KC_BSPC    0x002A
#endif
#ifndef KC_DEL
#define KC_DEL     0x004C
#endif
#ifndef KC_UP
#define KC_UP      0x0052
#endif
#ifndef KC_DOWN
#define KC_DOWN    0x0051
#endif
#ifndef KC_LEFT
#define KC_LEFT    0x0050
#endif
#ifndef KC_RIGHT
#define KC_RIGHT   0x004F
#endif
#ifndef KC_HOME
#define KC_HOME    0x004A
#endif
#ifndef KC_END
#define KC_END     0x004D
#endif

/* ---- QMK modifier macros ---- */
#ifndef LCTL
#define LCTL(kc)   (0x0100 | (kc))
#endif
#ifndef LSFT
#define LSFT(kc)   (0x0200 | (kc))
#endif

/* ---- Config ---- */
/* Whether vim modal starts enabled on module load. */
#ifndef VIM_MODAL_DEFAULT_ENABLED
#define VIM_MODAL_DEFAULT_ENABLED 1
#endif

/* Maximum depth of nested insert-mode entries (when Enter is pressed
 * from NORMAL it enters INSERT via 'o' path — not tracked here,
 * just a doc note for future expansion). */
