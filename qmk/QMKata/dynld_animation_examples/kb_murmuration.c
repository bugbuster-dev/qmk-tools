#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define BIRD_COUNT 24
#define MAX_SPEED_Q8 150
#define EDGE_MARGIN_Q8 (16 << 8)
#define EDGE_FORCE_Q8 18
#define SEPARATION_RADIUS_Q8 (11 << 8)
#define SEPARATION_RADIUS (SEPARATION_RADIUS_Q8 >> 8)
#define SEPARATION_RADIUS_SQ (SEPARATION_RADIUS * SEPARATION_RADIUS)
#define RENDER_RADIUS 18
#define RENDER_RADIUS_SQ (RENDER_RADIUS * RENDER_RADIUS)

typedef struct {
    int32_t x;
    int32_t y;
    int16_t vx;
    int16_t vy;
} bird_t;

static bird_t birds[BIRD_COUNT];
static uint16_t cached_max_x = 0;
static uint16_t cached_max_y = 0;
static bool initialized = false;

static inline int16_t clamp_speed(int16_t v) {
    if (v > MAX_SPEED_Q8) return MAX_SPEED_Q8;
    if (v < -MAX_SPEED_Q8) return -MAX_SPEED_Q8;
    return v;
}

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env, effect_params_t *params) {
    if (!initialized) {
        for (int led = 0; led < RGB_MATRIX_LED_COUNT; led++) {
            if (anim_env->led_config->point[led].x > cached_max_x) cached_max_x = anim_env->led_config->point[led].x;
            if (anim_env->led_config->point[led].y > cached_max_y) cached_max_y = anim_env->led_config->point[led].y;
        }

        uint32_t seed = anim_env->time | 1u;
        for (int i = 0; i < BIRD_COUNT; i++) {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            birds[i].x = (int32_t)anim_env->math_funs->mod((int)(seed >> 8), cached_max_x + 1) << 8;

            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            birds[i].y = (int32_t)anim_env->math_funs->mod((int)(seed >> 8), cached_max_y + 1) << 8;

            birds[i].vx = (int16_t)(((i & 3) - 1) * 32);
            birds[i].vy = (int16_t)((((i >> 2) & 3) - 1) * 24);
        }
        initialized = true;
    }

    int32_t bound_x_q8 = (int32_t)cached_max_x << 8;
    int32_t bound_y_q8 = (int32_t)cached_max_y << 8;
    int32_t center_x = 0;
    int32_t center_y = 0;
    int32_t avg_vx = 0;
    int32_t avg_vy = 0;

    for (int i = 0; i < BIRD_COUNT; i++) {
        center_x += birds[i].x;
        center_y += birds[i].y;
        avg_vx += birds[i].vx;
        avg_vy += birds[i].vy;
    }

    center_x /= BIRD_COUNT;
    center_y /= BIRD_COUNT;
    avg_vx /= BIRD_COUNT;
    avg_vy /= BIRD_COUNT;

    for (int i = 0; i < BIRD_COUNT; i++) {
        bird_t *b = &birds[i];
        int32_t separate_x = 0;
        int32_t separate_y = 0;

        for (int j = 0; j < BIRD_COUNT; j++) {
            if (i == j) continue;

            int16_t dx = (int16_t)((b->x - birds[j].x) >> 8);
            int16_t dy = (int16_t)((b->y - birds[j].y) >> 8);
            int32_t dist_sq = (int32_t)dx * dx + (int32_t)dy * dy;
            if (dist_sq > 0 && dist_sq < SEPARATION_RADIUS_SQ) {
                separate_x += dx;
                separate_y += dy;
            }
        }

        int16_t ax = (int16_t)((center_x - b->x) >> 8);
        int16_t ay = (int16_t)((center_y - b->y) >> 8);

        ax = (ax >> 3) + (int16_t)((avg_vx - b->vx) >> 3) + (int16_t)(separate_x << 4);
        ay = (ay >> 3) + (int16_t)((avg_vy - b->vy) >> 3) + (int16_t)(separate_y << 4);

        uint8_t flutter = (uint8_t)(((anim_env->time >> 6) + i * 17) & 7);
        ax += (int16_t)flutter - 3;
        ay += 3 - (int16_t)((flutter + i) & 7);

        if (b->x < EDGE_MARGIN_Q8) ax += EDGE_FORCE_Q8;
        if (b->x > bound_x_q8 - EDGE_MARGIN_Q8) ax -= EDGE_FORCE_Q8;
        if (b->y < EDGE_MARGIN_Q8) ay += EDGE_FORCE_Q8;
        if (b->y > bound_y_q8 - EDGE_MARGIN_Q8) ay -= EDGE_FORCE_Q8;

        b->vx = clamp_speed(b->vx + ax);
        b->vy = clamp_speed(b->vy + ay);
        b->x += b->vx;
        b->y += b->vy;

        if (b->x < 0) {
            b->x = 0;
            if (b->vx < 0) b->vx = -b->vx >> 1;
        } else if (b->x > bound_x_q8) {
            b->x = bound_x_q8;
            if (b->vx > 0) b->vx = -b->vx >> 1;
        }

        if (b->y < 0) {
            b->y = 0;
            if (b->vy < 0) b->vy = -b->vy >> 1;
        } else if (b->y > bound_y_q8) {
            b->y = bound_y_q8;
            if (b->vy > 0) b->vy = -b->vy >> 1;
        }
    }

    for (int led = 0; led < RGB_MATRIX_LED_COUNT; led++) {
        int16_t lx = anim_env->led_config->point[led].x;
        int16_t ly = anim_env->led_config->point[led].y;
        uint16_t density = 0;

        for (int i = 0; i < BIRD_COUNT; i++) {
            int16_t dx = (int16_t)(birds[i].x >> 8) - lx;
            int16_t dy = (int16_t)(birds[i].y >> 8) - ly;
            int32_t dist_sq = (int32_t)dx * dx + (int32_t)dy * dy;
            if (dist_sq < RENDER_RADIUS_SQ) {
                density += (uint16_t)(72 - (dist_sq >> 2));
            }
        }

        if (density > 255) density = 255;
        HSV hsv = {
            .h = (uint8_t)(145 + (density >> 4)),
            .s = 90,
            .v = (uint8_t)density,
        };
        anim_env->set_color_hsv(led, hsv);
    }

    return false;
}
