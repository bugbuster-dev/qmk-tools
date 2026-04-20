#ifndef MODULE_API_H
#define MODULE_API_H

#include <stdint.h>
#include <stdbool.h>

/* Hook indices - must match firmware module_loader.h */
#define MODULE_HOOK_COMBO_SHOULD_TRIGGER  0
#define MODULE_HOOK_PROCESS_COMBO_EVENT   1
#define MODULE_HOOK_GET_COMBO_TERM        2
#define MODULE_HOOK_INIT                  3
#define MODULE_HOOK_DEINIT                4
#define MODULE_HOOK_MAX                   16

/* Place the hook table in the .hook_table section */
#define MODULE_HOOK_TABLE __attribute__((section(".hook_table"), used))

/* Minimal type stubs - match QMK struct layout for accessed fields only.
   Module code uses these instead of including full QMK headers. */
typedef struct { const uint16_t *keys; uint16_t keycode; } combo_t;
typedef struct { struct { uint16_t key; } event; } keyrecord_t;
typedef uint32_t layer_state_t;

extern layer_state_t layer_state;

/* Default combo term if not defined */
#ifndef COMBO_TERM
#define COMBO_TERM 50
#endif

#endif /* MODULE_API_H */
