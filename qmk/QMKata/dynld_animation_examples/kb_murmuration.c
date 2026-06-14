#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

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
