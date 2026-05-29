#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define LASER_LENGTH 8
#define LASER_COUNT  3
#define LASER_R 255
#define LASER_G 0
#define LASER_B 0

static inline uint8_t _lcg(uint32_t *s) {
    *s = *s * 1103515245 + 12345;
    return (uint8_t)((*s >> 16) & 0xFF);
}

typedef struct {
    uint8_t row;
    uint8_t pos;
} laser_t;

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env,
                         effect_params_t *params) {
    static laser_t lasers[LASER_COUNT];
    static uint32_t rng;

    if (params->init) {
        rng = anim_env->time;
        for (uint8_t i = 0; i < LASER_COUNT; i++) {
            lasers[i].row = _lcg(&rng) % MATRIX_ROWS;
            lasers[i].pos = _lcg(&rng) % MATRIX_COLS;
        }
    }

    for (uint8_t i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
        anim_env->set_color(i, 0, 0, 0);
    }

    for (uint8_t l = 0; l < LASER_COUNT; l++) {
        uint8_t row = lasers[l].row;
        uint8_t pos = lasers[l].pos;

        for (uint8_t c = 0; c < MATRIX_COLS; c++) {
            uint8_t led = anim_env->led_config->matrix_co[row][c];
            if (led == 255) continue;

            uint8_t dist = (c <= pos) ? (pos - c) : (MATRIX_COLS - pos + c);
            if (dist < LASER_LENGTH) {
                uint8_t intensity = (LASER_LENGTH - dist) * 255 / LASER_LENGTH;
                anim_env->set_color(led,
                    (uint8_t)((LASER_R * intensity) >> 8),
                    (uint8_t)((LASER_G * intensity) >> 8),
                    (uint8_t)((LASER_B * intensity) >> 8));
            }
        }

        lasers[l].pos = (lasers[l].pos + 1) % MATRIX_COLS;
    }

    return false;
}
