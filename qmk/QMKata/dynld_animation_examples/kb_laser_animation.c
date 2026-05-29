#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define LASER_LENGTH    8
#define LASER_COUNT     2
#define LASER_RED_R     255
#define LASER_RED_G       0
#define LASER_RED_B       0
#define LASER_CYAN_R      0
#define LASER_CYAN_G    255
#define LASER_CYAN_B    255

typedef struct {
    uint8_t row;
    uint8_t pos;
    uint8_t dir;
    uint8_t speed;
} laser_t;

static inline uint8_t _lcg_rand(uint32_t *seed) {
    *seed = *seed * 1103515245 + 12345;
    return (uint8_t)((*seed >> 16) & 0xFF);
}

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env,
                         effect_params_t *params) {
    static laser_t lasers[LASER_COUNT];
    static uint32_t rng_seed;
    uint8_t led_max = RGB_MATRIX_LED_COUNT;
    uint8_t speed = anim_env->rgb_config->speed;

    if (params->init) {
        rng_seed = anim_env->time;
        for (uint8_t i = 0; i < LASER_COUNT; i++) {
            lasers[i].row = _lcg_rand(&rng_seed) % MATRIX_ROWS;
            lasers[i].pos = _lcg_rand(&rng_seed);
            lasers[i].dir = (_lcg_rand(&rng_seed) & 1);
            lasers[i].speed = (speed >> 2) + 1;
        }
    }

    for (uint8_t i = 0; i < led_max; i++) {
        anim_env->set_color(i, 0, 0, 0);
    }

    for (uint8_t l = 0; l < LASER_COUNT; l++) {
        uint8_t row = lasers[l].row;
        uint8_t pos = lasers[l].pos;
        uint8_t dir = lasers[l].dir;
        uint8_t spd = lasers[l].speed;

        for (uint8_t i = 0; i < led_max; i++) {
            uint8_t led_row = anim_env->led_config->point[i].y / (240 / MATRIX_ROWS);
            uint8_t led_col = anim_env->led_config->point[i].x / (320 / MATRIX_COLS);
            if (led_row != row) continue;

            uint8_t dist;
            if (dir == 0) {
                dist = (led_col < pos) ? (pos - led_col) : (256 - pos + led_col);
            } else {
                dist = (led_col > pos) ? (led_col - pos) : (led_col + (256 - pos));
            }

            if (dist < LASER_LENGTH) {
                uint8_t intensity = (LASER_LENGTH - dist) * 255 / LASER_LENGTH;
                if (dir == 0) {
                    anim_env->set_color(i,
                        (uint8_t)((LASER_RED_R * intensity) >> 8),
                        (uint8_t)((LASER_RED_G * intensity) >> 8),
                        (uint8_t)((LASER_RED_B * intensity) >> 8));
                } else {
                    anim_env->set_color(i,
                        (uint8_t)((LASER_CYAN_R * intensity) >> 8),
                        (uint8_t)((LASER_CYAN_G * intensity) >> 8),
                        (uint8_t)((LASER_CYAN_B * intensity) >> 8));
                }
            }
        }

        if (dir == 0) {
            lasers[l].pos = (pos + spd) & 0xFF;
        } else {
            lasers[l].pos = (pos - spd) & 0xFF;
        }
    }

    return false;
}
