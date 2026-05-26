/* Matrix Rain dynld animation — ModuleBuild pipeline.
 *
 * Falling green rain columns mapped by LED x-coordinate. */

#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define RAIN_COLS              14
#define RAIN_ROWS              6
#define RAIN_SPEED             8
#define RAIN_TRAIL_MIN         3
#define RAIN_TRAIL_MAX         8
#define RAIN_GREEN_R           0
#define RAIN_GREEN_G           255
#define RAIN_GREEN_B           0
#define RAIN_HEAD_BRIGHTNESS   255

static uint8_t col_position[RAIN_COLS];
static uint8_t col_speed[RAIN_COLS];
static uint8_t col_trail[RAIN_COLS];
static uint8_t frame_counter;
static uint32_t lcg_seed;
static bool initialized;

static uint32_t lcg_next(void) {
    lcg_seed = lcg_seed * 1103515245u + 12345u;
    return lcg_seed;
}

static void matrix_init(dynld_custom_animation_env_t *anim_env) {
    lcg_seed = (uint32_t)anim_env->time ^ 0x4B7E1131u;
    for (uint8_t c = 0; c < RAIN_COLS; c++) {
        col_position[c] = lcg_next() % RAIN_ROWS;
        col_speed[c] = (lcg_next() % 3) + 1;
        col_trail[c] = (lcg_next() % (RAIN_TRAIL_MAX - RAIN_TRAIL_MIN + 1)) + RAIN_TRAIL_MIN;
    }
    initialized = true;
}

static void advance_drops(void) {
    for (uint8_t c = 0; c < RAIN_COLS; c++) {
        uint8_t prev = col_position[c];
        col_position[c] = (col_position[c] + col_speed[c]) % RAIN_ROWS;
        if (col_position[c] < prev) {
            col_speed[c] = (lcg_next() % 3) + 1;
            col_trail[c] = (lcg_next() % (RAIN_TRAIL_MAX - RAIN_TRAIL_MIN + 1)) + RAIN_TRAIL_MIN;
        }
    }
}

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env,
                         effect_params_t *params) {
    if (!initialized) matrix_init(anim_env);

    frame_counter++;
    if (frame_counter >= RAIN_SPEED) {
        frame_counter = 0;
        advance_drops();
    }

    uint8_t leds = RGB_MATRIX_LED_COUNT;
    for (uint8_t i = 0; i < leds; i++) {
        uint8_t col = anim_env->led_config->point[i].x >> 4;
        if (col >= RAIN_COLS) col = RAIN_COLS - 1;

        uint8_t row = anim_env->led_config->point[i].y >> 4;
        if (row >= RAIN_ROWS) row = RAIN_ROWS - 1;

        uint8_t pos = col_position[col];
        uint8_t trail = col_trail[col];

        uint8_t r = 0, g = 0, b = 0;
        int8_t diff = (int8_t)pos - (int8_t)row;
        if (diff >= 0 && diff < (int8_t)trail) {
            uint8_t brightness = RAIN_HEAD_BRIGHTNESS / (diff + 1);
            r = (RAIN_GREEN_R * brightness) >> 8;
            g = (RAIN_GREEN_G * brightness) >> 8;
            b = (RAIN_GREEN_B * brightness) >> 8;
        }
        anim_env->set_color(i, r, g, b);
    }
    return false;
}
