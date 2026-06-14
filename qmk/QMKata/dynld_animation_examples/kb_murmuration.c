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
bool effect_runner_func(void) {
    return false;
}
