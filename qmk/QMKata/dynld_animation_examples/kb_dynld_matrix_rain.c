/* Matrix Rain dynld animation — ModuleBuild pipeline.
 *
 * Falling green rain columns mapped by LED x-coordinate. */

#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define MATRIX_COLS            14
#define MATRIX_ROWS            6
#define MATRIX_SPEED           8
#define MATRIX_TRAIL_MIN       3
#define MATRIX_TRAIL_MAX       8
#define MATRIX_GREEN_R         0
#define MATRIX_GREEN_G         255
#define MATRIX_GREEN_B         0
#define MATRIX_HEAD_BRIGHTNESS 255

static uint8_t col_position[MATRIX_COLS];
static uint8_t col_speed[MATRIX_COLS];
static uint8_t col_trail[MATRIX_COLS];
static uint8_t frame_counter;
static uint32_t lcg_seed;
static bool initialized;

static uint32_t lcg_next(void) {
    lcg_seed = lcg_seed * 1103515245u + 12345u;
    return lcg_seed;
}

static void matrix_init(dynld_custom_animation_env_t *anim_env) {
    lcg_seed = (uint32_t)anim_env->time ^ 0x4B7E1131u;
    for (uint8_t c = 0; c < MATRIX_COLS; c++) {
        col_position[c] = lcg_next() % MATRIX_ROWS;
        col_speed[c] = (lcg_next() % 3) + 1;
        col_trail[c] = (lcg_next() % (MATRIX_TRAIL_MAX - MATRIX_TRAIL_MIN + 1)) + MATRIX_TRAIL_MIN;
    }
    initialized = true;
}

static void advance_drops(void) {
    for (uint8_t c = 0; c < MATRIX_COLS; c++) {
        uint8_t prev = col_position[c];
        col_position[c] = (col_position[c] + col_speed[c]) % MATRIX_ROWS;
        if (col_position[c] < prev) {
            col_speed[c] = (lcg_next() % 3) + 1;
            col_trail[c] = (lcg_next() % (MATRIX_TRAIL_MAX - MATRIX_TRAIL_MIN + 1)) + MATRIX_TRAIL_MIN;
        }
    }
}
