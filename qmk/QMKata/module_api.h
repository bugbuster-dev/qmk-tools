#ifndef MODULE_API_H
#define MODULE_API_H

#include <stdint.h>
#include <stdbool.h>

/* Hook indices - must match firmware module_loader.h */
#define MODULE_HOOK_COMBO_SHOULD_TRIGGER           0
#define MODULE_HOOK_PROCESS_COMBO_EVENT            1
#define MODULE_HOOK_GET_COMBO_TERM                 2
#define MODULE_HOOK_INIT                           3
#define MODULE_HOOK_DEINIT                         4
#define MODULE_HOOK_GET_COMBO_MUST_HOLD            5
#define MODULE_HOOK_GET_COMBO_MUST_TAP             6
#define MODULE_HOOK_GET_COMBO_MUST_PRESS_IN_ORDER  7
#define MODULE_HOOK_PROCESS_COMBO_KEY_RELEASE      8
#define MODULE_HOOK_PROCESS_COMBO_KEY_REPRESS      9
#define MODULE_HOOK_COMBO_REF_FROM_LAYER          10
#define MODULE_HOOK_MAX                           16

/* Value a module's init function must return for the firmware loader
   to consider the init call successful. Must match the firmware's
   MODULE_INIT_MAGIC in module_loader.h.

   Init signature:   uint32_t module_init(void)
   Deinit signature: uint32_t module_deinit(void)

   Module code accesses its own .rodata through normal C references;
   the loader has already rebased literal-pool addresses to the slot's
   runtime location, so no module_base parameter is needed.

   Init must return this magic; deinit's return is logged by the firmware but not checked. */
#define MODULE_INIT_MAGIC                         0x600DBEEFu

/* mprintf: gated diagnostic print for module code.

   Signature is printf-compatible (except the return type is void).
   No-op unless the user sets debug_config_user.module = 1 on the
   device; otherwise forwards to the firmware's printf (the same
   console endpoint used by QMK core).

   Why not use QMK's xprintf() directly? xprintf is a preprocessor
   macro that expands to printf, not a real symbol, so modules cannot
   resolve it through the host's .map-based symbol linkage. Do not
   #include quantum/logging/print.h here — it pulls in firmware-only
   headers that break the module build.

   Output is automatically prefixed with "[mod] " so module console
   output is distinguishable from firmware core output. Use mprintf
   for routine diagnostics that shouldn't spam the console by default.
   Modules that need unconditional output (e.g. fatal error paths) can
   still extern-declare printf directly, which bypasses the gate. */
extern void mprintf(const char *fmt, ...);

/* Place the hook table in the .hook_table section */
#define MODULE_HOOK_TABLE __attribute__((section(".hook_table"), used))

/* Minimal type stubs - keep layout-compatible with QMK for accessed APIs. */
typedef struct { const uint16_t *keys; uint16_t keycode; } combo_t;

typedef struct {
    uint8_t col;
    uint8_t row;
} keypos_t;

typedef enum keyevent_type_t {
    TICK_EVENT = 0,
    KEY_EVENT = 1,
    ENCODER_CW_EVENT = 2,
    ENCODER_CCW_EVENT = 3,
    COMBO_EVENT = 4,
    DIP_SWITCH_ON_EVENT = 5,
    DIP_SWITCH_OFF_EVENT = 6,
} keyevent_type_t;

typedef struct {
    keypos_t key;
    uint16_t time;
    keyevent_type_t type;
    bool pressed;
} keyevent_t;

typedef struct keyrecord_t {
    keyevent_t event;
    uint16_t keycode;
} keyrecord_t;

typedef uint16_t layer_state_t;

extern layer_state_t layer_state;
extern layer_state_t default_layer_state;

/* Default combo term if not defined */
#ifndef COMBO_TERM
#define COMBO_TERM 50
#endif

#endif /* MODULE_API_H */
