/* pre_record_logger.c — example module demonstrating PRE_PROCESS_RECORD hook.
 *
 * Claims MODULE_KEY_HOOK_PRE_PROCESS_RECORD and logs every keypress
 * via mprintf. Works without any keymap changes (strong override of
 * QMK's pre_process_record_user). Returns true to let processing
 * continue — this is a logger, not a filter.
 *
 * To test:
 * 1. Build with qmk-tools: module_build.py pre_record_logger.c
 * 2. Upload to a free slot (e.g. slot 4).
 * 3. Enable module debug: qmk console → debug_config module=1
 * 4. Type on keyboard — see "[mod] key: KC_A press" etc. on console.
 */

#include "module_api.h"

static uint32_t module_init(void) {
    mprintf("pre_record_logger loaded\n");
    return MODULE_INIT_MAGIC;
}

static bool pre_process_record(uint16_t keycode, keyrecord_t *record) {
    if (record->event.pressed) {
        mprintf("key: %04X press\n", keycode);
    } else {
        mprintf("key: %04X release\n", keycode);
    }
    return true;  /* let processing continue */
}

MODULE_HOOK_TABLE
const void *module_hook_table[MODULE_HOOK_MAX] = {
    [MODULE_HOOK_INIT] = module_init,
    [MODULE_KEY_HOOK_PRE_PROCESS_RECORD] = pre_process_record,
};
