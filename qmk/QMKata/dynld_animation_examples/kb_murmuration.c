#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"
#include <math.h>

#ifndef M_PI
#define M_PI 3.1415926535f
#endif

static inline int16_t q_sin(int16_t theta) {
    return (int16_t)(sinf((float)theta * (2.0f * M_PI / 65536.0f)) * 256.0f);
}

static inline int16_t q_cos(int16_t theta) {
    return (int16_t)(cosf((float)theta * (2.0f * M_PI / 65536.0f)) * 256.0f);
}

typedef struct {
    int32_t x;
    int32_t y;
} particle_t;

static particle_t particles[64];
static uint8_t cached_max_x = 0;
static uint8_t cached_max_y = 0;
static bool initialized = false;

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env, effect_params_t *params) {
    if (!initialized) {
        for (int i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
            if (anim_env->led_config->point[i].x > cached_max_x) cached_max_x = anim_env->led_config->point[i].x;
            if (anim_env->led_config->point[i].y > cached_max_y) cached_max_y = anim_env->led_config->point[i].y;
        }
        uint32_t seed = anim_env->time;
        for (int i = 0; i < 64; i++) {
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF;
            particles[i].x = (int16_t)(seed % (cached_max_x + 1)) << 8;
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF;
            particles[i].y = (int16_t)(seed % (cached_max_y + 1)) << 8;
        }
        initialized = true;
    }

    uint32_t t = anim_env->time / 10;
    const uint16_t scale1 = 100;
    const uint16_t scale2 = 200;

    for (int i = 0; i < 64; i++) {
        particle_t *p = &particles[i];
        int16_t x_int = p->x >> 8;
        int16_t y_int = p->y >> 8;

        int16_t dx = q_sin((int16_t)(t + y_int * scale1)) + q_cos((int16_t)(t + x_int * scale2));
        int16_t dy = q_cos((int16_t)(t + x_int * scale1)) + q_sin((int16_t)(t + y_int * scale2));
        
        p->x += dx;
        p->y += dy;

        int32_t bound_x_q8 = (int32_t)(cached_max_x + 1) << 8;
        int32_t bound_y_q8 = (int32_t)(cached_max_y + 1) << 8;

        while (p->x < 0) p->x += bound_x_q8;
        while (p->x >= bound_x_q8) p->x -= bound_x_q8;
        while (p->y < 0) p->y += bound_y_q8;
        while (p->y >= bound_y_q8) p->y -= bound_y_q8;
    }

    return false;
}
