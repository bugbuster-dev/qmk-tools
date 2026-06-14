#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"
static const int16_t sin_lut[256] = {
    0, 6, 13, 19, 25, 31, 38, 44, 50, 56, 62, 68, 74, 80, 86, 92, 98, 104, 109, 115, 121, 126, 132, 137, 142, 147, 152, 157, 162, 167, 172, 177, 181, 185, 190, 194, 198, 202, 206, 209, 213, 216, 220, 223, 226, 229, 231, 234, 237, 239, 241, 243, 245, 247, 248, 250, 251, 252, 253, 254, 255, 255, 256, 256, 256, 256, 256, 255, 255, 254, 253, 252, 251, 250, 248, 247, 245, 243, 241, 239, 237, 234, 231, 229, 226, 223, 220, 216, 213, 209, 206, 202, 198, 194, 190, 185, 181, 177, 172, 167, 162, 157, 152, 147, 142, 137, 132, 126, 121, 115, 109, 104, 98, 92, 86, 80, 74, 68, 62, 56, 50, 44, 38, 31, 25, 19, 13, 6, 0, -6, -13, -19, -25, -31, -38, -44, -50, -56, -62, -68, -74, -80, -86, -92, -98, -104, -109, -115, -121, -126, -132, -137, -142, -147, -152, -157, -162, -167, -172, -177, -181, -185, -190, -194, -198, -202, -206, -209, -213, -216, -220, -223, -226, -229, -231, -234, -237, -239, -241, -243, -245, -247, -248, -250, -251, -252, -253, -254, -255, -255, -256, -256, -256, -256, -256, -255, -255, -254, -253, -252, -251, -250, -248, -247, -245, -243, -241, -239, -237, -234, -231, -229, -226, -223, -220, -216, -213, -209, -206, -202, -198, -194, -190, -185, -181, -177, -172, -167, -162, -157, -152, -147, -142, -137, -132, -126, -121, -115, -109, -104, -98, -92, -86, -80, -74, -68, -62, -56, -50, -44, -38, -31, -25, -19, -13, -6
};

static inline int16_t q_sin(int16_t theta) {
    return sin_lut[theta & 0xFF];
}

static inline int16_t q_cos(int16_t theta) {
    return q_sin(theta + 64);
}

typedef struct {
    int32_t x;
    int32_t y;
    int16_t vx;  // velocity Q8.8
    int16_t vy;  // velocity Q8.8
} particle_t;

static particle_t particles[64];
static uint16_t cached_max_x = 0;
static uint16_t cached_max_y = 0;
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
            particles[i].vx = 0;
            particles[i].vy = 0;
        }
        initialized = true;
    }

    uint32_t t = anim_env->time / 80;
    int32_t bound_x_q8 = (int32_t)(cached_max_x + 1) << 8;
    int32_t bound_y_q8 = (int32_t)(cached_max_y + 1) << 8;

    for (int i = 0; i < RGB_MATRIX_LED_COUNT; i++) {
        HSV clear = {0, 0, 0};
        anim_env->set_color_hsv(i, clear);
    }

    for (int i = 0; i < 64; i++) {
        particle_t *p = &particles[i];
        int16_t x_int = p->x >> 8;
        int16_t y_int = p->y >> 8;

        /* Smooth flow field - low spatial frequency for large-scale swirls */
        int16_t fx = q_sin((int16_t)(t + (x_int * 8 + y_int * 3))) +
                     q_cos((int16_t)(t + (x_int * 5 - y_int * 7)));
        int16_t fy = q_cos((int16_t)(t + (x_int * 6 + y_int * 2))) +
                     q_sin((int16_t)(t - (x_int * 4 + y_int * 9)));

        /* Blend flow direction into existing velocity (inertia) */
        p->vx = (p->vx * 14 + fx) >> 4;
        p->vy = (p->vy * 14 + fy) >> 4;

        /* Scale velocity down for graceful movement */
        int16_t dx = p->vx >> 2;
        int16_t dy = p->vy >> 2;

        p->x += dx;
        p->y += dy;

        while (p->x < 0) p->x += bound_x_q8;
        while (p->x >= bound_x_q8) p->x -= bound_x_q8;
        while (p->y < 0) p->y += bound_y_q8;
        while (p->y >= bound_y_q8) p->y -= bound_y_q8;

        int32_t min_dist_sq = 0x7FFFFFFF;
        int closest_led = -1;
        int16_t px = p->x >> 8;
        int16_t py = p->y >> 8;

        for (int j = 0; j < RGB_MATRIX_LED_COUNT; j++) {
            int16_t lx = anim_env->led_config->point[j].x;
            int16_t ly = anim_env->led_config->point[j].y;
            int32_t ddx = px - lx;
            int32_t ddy = py - ly;
            int32_t dist_sq = ddx * ddx + ddy * ddy;
            if (dist_sq < min_dist_sq) {
                min_dist_sq = dist_sq;
                closest_led = j;
            }
        }

        if (closest_led != -1) {
            /* Hue from flow angle, brightness from speed */
            int32_t vel_sq = (int32_t)dx * dx + (int32_t)dy * dy;
            uint8_t hue = (uint8_t)((px * 13 + py * 29 + t * 3) & 0xFF);
            uint8_t val = (uint8_t)((vel_sq >> 4) > 255 ? 255 : (vel_sq >> 4));
            if (val < 64) val = 64;
            HSV hsv = {
                .h = hue,
                .s = 200,
                .v = val
            };
            anim_env->set_color_hsv(closest_led, hsv);
        }
    }

    return false;
}
