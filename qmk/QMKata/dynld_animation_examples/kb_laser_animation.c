#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define LASER_LENGTH 8
#define LASER_SPEED  1
#define RED_R 255
#define RED_G 0
#define RED_B 0
#define BLUE_R 0
#define BLUE_G 0
#define BLUE_B 255

static inline uint8_t _lcg(uint32_t *s) {
    *s = *s * 1103515245 + 12345;
    return (uint8_t)((*s >> 16) & 0xFF);
}

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env,
                         effect_params_t *params) {
    static uint8_t row_r;
    static uint8_t pos_r;
    static uint8_t row_b;
    static uint8_t pos_b;
    static uint8_t frame;
    static uint32_t rng;

    if (params->init) {
        rng = anim_env->time;
        row_r = _lcg(&rng) % MATRIX_ROWS;
        pos_r = 0;
        row_b = _lcg(&rng) % MATRIX_ROWS;
        while (row_b == row_r) {
            row_b = _lcg(&rng) % MATRIX_ROWS;
        }
        pos_b = MATRIX_COLS - 1;
    }

    for (uint8_t i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
        anim_env->set_color(i, 0, 0, 0);
    }

    for (uint8_t c = 0; c < MATRIX_COLS; c++) {
        uint8_t led = anim_env->led_config->matrix_co[row_r][c];
        if (led == 255) continue;

        uint8_t dist = (c <= pos_r) ? (pos_r - c) : (MATRIX_COLS - pos_r + c);
        if (dist < LASER_LENGTH) {
            uint8_t intensity = (LASER_LENGTH - dist) * 255 / LASER_LENGTH;
            anim_env->set_color(led,
                (uint8_t)((RED_R * intensity) >> 8),
                (uint8_t)((RED_G * intensity) >> 8),
                (uint8_t)((RED_B * intensity) >> 8));
        }
    }

    for (uint8_t c = 0; c < MATRIX_COLS; c++) {
        uint8_t led = anim_env->led_config->matrix_co[row_b][c];
        if (led == 255) continue;

        uint8_t dist = (c >= pos_b) ? (c - pos_b) : (c + MATRIX_COLS - pos_b);
        if (dist < LASER_LENGTH) {
            uint8_t intensity = (LASER_LENGTH - dist) * 255 / LASER_LENGTH;
            anim_env->set_color(led,
                (uint8_t)((BLUE_R * intensity) >> 8),
                (uint8_t)((BLUE_G * intensity) >> 8),
                (uint8_t)((BLUE_B * intensity) >> 8));
        }
    }

    frame++;
    if (frame >= LASER_SPEED) {
        frame = 0;
        pos_r = (pos_r + 1) % MATRIX_COLS;
        if (pos_r == 0) {
            row_r = _lcg(&rng) % MATRIX_ROWS;
        }
        pos_b = (pos_b + MATRIX_COLS - 1) % MATRIX_COLS;
        if (pos_b == MATRIX_COLS - 1) {
            row_b = _lcg(&rng) % MATRIX_ROWS;
        }
    }

    return false;
}
