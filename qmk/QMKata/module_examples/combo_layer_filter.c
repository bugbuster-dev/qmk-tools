#include "module_api.h"

bool combo_should_trigger(uint16_t combo_index, combo_t *combo,
                          uint16_t keycode, keyrecord_t *record) {
    (void)combo_index;
    (void)combo;
    (void)keycode;
    (void)record;

    if (layer_state & (1u << 2)) {
        return false;
    }
    return true;
}

MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_COMBO_HOOK_SHOULD_TRIGGER] = combo_should_trigger,
};
