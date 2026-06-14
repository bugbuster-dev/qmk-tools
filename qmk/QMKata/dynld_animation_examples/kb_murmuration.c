#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"
#include <math.h>

#ifndef M_PI
#define M_PI 3.1415926535f
#endif

static inline int16_t q_sin(dynld_custom_animation_env_t *env, int16_t theta) {
    return (int16_t)(sinf((float)theta * (2.0f * M_PI / 65536.0f)) * 256.0f);
}

static inline int16_t q_cos(dynld_custom_animation_env_t *env, int16_t theta) {
    return (int16_t)(cosf((float)theta * (2.0f * M_PI / 65536.0f)) * 256.0f);
}

typedef struct {
    int16_t x;
    int16_t y;
} particle_t;

static particle_t particles[64];
static bool initialized = false;

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env, effect_params_t *params) {
    uint8_t max_x = 0;
    uint8_t max_y = 0;
    for (int i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
        if (anim_env->led_config->point[i].x > max_x) max_x = anim_env->led_config->point[i].x;
        if (anim_env->led_config->point[i].y > max_y) max_y = anim_env->led_config->point[i].y;
    }

    if (!initialized) {
        uint32_t seed = anim_env->time;
        for (int i = 0; i < 64; i++) {
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF;
            particles[i].x = (int16_t)(seed % (max_x + 1)) << 8;
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF;
            particles[i].y = (int16_t)(seed % (max_y + 1)) << 8;
        }
        initialized = true;
    }

    uint32_t t = anim_env->time;
    const uint16_t scale1 = 100;
    const uint16_t scale2 = 200;

    for (int i = 0; i < 64; i++) {
        particle_t *p = &particles[i];
        int16_t x_int = p->x >> 8;
        int16_t y_int = p->y >> 8;

        int16_t dx = q_sin(anim_env, (int16_t)(t + y_int * scale1)) + q_cos(anim_env, (int16_t)(t + x_int * scale2));
        int16_t dy = q_cos(anim_env, (int16_t)(t + x_int * scale1)) + q_sin(anim_env, (int16_t)(t + y_int * scale2));
        
        p->x += dx;
        p->y += dy;

        int16_t bound_x_q8 = (int16_t)(max_x + 1) << 8;
        int16_t bound_y_q8 = (int16_t)(max_y + 1) << 8;

        if (p->x < 0) p->x += bound_x_q8;
        else if (p->x >= bound_x_q8) p->x -= bound_x_q8;
        if (p->y < 0) p->y += bound_y_q8;
        else if (p->y >= bound_y_q8) p->y -= bound_y_q8;
    }

    return false;
}
