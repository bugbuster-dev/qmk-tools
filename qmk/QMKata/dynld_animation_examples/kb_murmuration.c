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
    return false;
}
