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
    uint8_t frame;
} laser_t;

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env,
                         effect_params_t *params) {
    static laser_t lasers[LASER_COUNT];
    uint8_t speed = anim_env->rgb_config->speed;
    uint8_t skip = (speed >> 5) + 1;

    if (params->init) {
        uint8_t valid_rows[MATRIX_ROWS];
        uint8_t count = 0;
        for (uint8_t r = 0; r < MATRIX_ROWS; r++) {
            for (uint8_t c = 0; c < MATRIX_COLS; c++) {
                if (anim_env->led_config->matrix_co[r][c] != 255) {
                    valid_rows[count++] = r;
                    break;
                }
            }
        }
        if (count < 2) count = 2;
        uint32_t t = anim_env->time;
        lasers[0].row = valid_rows[t % count];
        lasers[0].pos = 0;
        lasers[0].dir = 0;
        lasers[0].frame = 0;
        lasers[1].row = valid_rows[(t / count) % count];
        if (lasers[1].row == lasers[0].row) {
            lasers[1].row = valid_rows[(t % count + 1) % count];
        }
        lasers[1].pos = 0;
        lasers[1].dir = 1;
        lasers[1].frame = 0;
    }

    for (uint8_t i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
        anim_env->set_color(i, 0, 0, 0);
    }

    for (uint8_t l = 0; l < LASER_COUNT; l++) {
        lasers[l].frame++;
        if (lasers[l].frame >= skip) {
            lasers[l].frame = 0;
            if (lasers[l].dir == 0) {
                lasers[l].pos = (lasers[l].pos + 1) % MATRIX_COLS;
            } else {
                lasers[l].pos = (lasers[l].pos + MATRIX_COLS - 1) % MATRIX_COLS;
            }
        }

        uint8_t row = lasers[l].row;
        uint8_t pos = lasers[l].pos;
        uint8_t dir = lasers[l].dir;

        for (uint8_t c = 0; c < MATRIX_COLS; c++) {
            uint8_t led = anim_env->led_config->matrix_co[row][c];
            if (led == 255) continue;

            uint8_t dist;
            if (dir == 0) {
                dist = (c <= pos) ? (pos - c) : (MATRIX_COLS - pos + c);
            } else {
                dist = (c >= pos) ? (c - pos) : (c + MATRIX_COLS - pos);
            }

            if (dist < LASER_LENGTH) {
                uint8_t intensity = (LASER_LENGTH - dist) * 255 / LASER_LENGTH;
                if (dir == 0) {
                    anim_env->set_color(led,
                        (uint8_t)((LASER_RED_R * intensity) >> 8),
                        (uint8_t)((LASER_RED_G * intensity) >> 8),
                        (uint8_t)((LASER_RED_B * intensity) >> 8));
                } else {
                    anim_env->set_color(led,
                        (uint8_t)((LASER_CYAN_R * intensity) >> 8),
                        (uint8_t)((LASER_CYAN_G * intensity) >> 8),
                        (uint8_t)((LASER_CYAN_B * intensity) >> 8));
                }
            }
        }
    }

    return false;
}
