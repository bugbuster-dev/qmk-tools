#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define BIRD_COUNT 24
#define MAX_SPEED_Q8 150
#define EDGE_MARGIN_Q8 (24 << 8)
#define EDGE_FORCE_Q8 18
#define MIGRATE_MARGIN_Q8 (40 << 8)
#define CRUISE_Q8 80
#define EDGE_FADE_MARGIN 32
#define MAX_DENSITY 220
#define PERCEPTION_RADIUS 34
#define PERCEPTION_RADIUS_SQ (PERCEPTION_RADIUS * PERCEPTION_RADIUS)
#define SEPARATION_RADIUS_Q8 (12 << 8)
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
static int8_t travel_dir = 0;
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

            birds[i].vx = CRUISE_Q8;
            birds[i].vy = (int16_t)((((i >> 2) & 3) - 1) * 16);
        }
        travel_dir = 1;
        initialized = true;
    }

    int32_t bound_x_q8 = (int32_t)cached_max_x << 8;
    int32_t bound_y_q8 = (int32_t)cached_max_y << 8;

    /* Migration: reverse the cruise direction when the flock's center
     * approaches a side. This drives net side-to-side travel without a
     * shared attractor point (which would collapse the flock to a clump). */
    int32_t center_x = 0;
    for (int i = 0; i < BIRD_COUNT; i++) center_x += birds[i].x;
    center_x /= BIRD_COUNT;

    if (center_x > bound_x_q8 - MIGRATE_MARGIN_Q8) travel_dir = -1;
    else if (center_x < MIGRATE_MARGIN_Q8) travel_dir = 1;

    int16_t cruise_vx = (int16_t)(travel_dir * CRUISE_Q8);

    for (int i = 0; i < BIRD_COUNT; i++) {
        bird_t *b = &birds[i];
        int32_t sum_cx = 0, sum_cy = 0;   /* neighbor positions (px) */
        int32_t sum_vx = 0, sum_vy = 0;   /* neighbor velocities (Q8) */
        int32_t sep_x = 0, sep_y = 0;     /* short-range repulsion (px) */
        int16_t count = 0;

        int16_t bxp = (int16_t)(b->x >> 8);
        int16_t byp = (int16_t)(b->y >> 8);

        /* Local neighborhood only — this is what produces murmuration
         * shimmer instead of a single rigid blob. */
        for (int j = 0; j < BIRD_COUNT; j++) {
            if (i == j) continue;

            int16_t dx = bxp - (int16_t)(birds[j].x >> 8);
            int16_t dy = byp - (int16_t)(birds[j].y >> 8);
            int32_t dist_sq = (int32_t)dx * dx + (int32_t)dy * dy;

            if (dist_sq < PERCEPTION_RADIUS_SQ) {
                count++;
                sum_cx += (int16_t)(birds[j].x >> 8);
                sum_cy += (int16_t)(birds[j].y >> 8);
                sum_vx += birds[j].vx;
                sum_vy += birds[j].vy;

                if (dist_sq < SEPARATION_RADIUS_SQ) {
                    sep_x += dx;
                    sep_y += dy;
                }
            }
        }

        int16_t coh_x = 0, coh_y = 0;   /* toward local center (px) */
        int16_t ali_x = 0, ali_y = 0;   /* match local heading (Q8) */
        if (count > 0) {
            coh_x = (int16_t)(anim_env->math_funs->div((int)sum_cx, count) - bxp);
            coh_y = (int16_t)(anim_env->math_funs->div((int)sum_cy, count) - byp);
            ali_x = (int16_t)(anim_env->math_funs->div((int)sum_vx, count) - b->vx);
            ali_y = (int16_t)(anim_env->math_funs->div((int)sum_vy, count) - b->vy);
        }

        /* Steering: separation (strong, short range) + alignment +
         * cohesion (weak) + migration cruise bias. */
        int16_t ax = (int16_t)(sep_x << 3) + (ali_x >> 2) + (coh_x >> 1) +
                     ((cruise_vx - b->vx) >> 3);
        int16_t ay = (int16_t)(sep_y << 3) + (ali_y >> 2) + (coh_y >> 1) +
                     ((-b->vy) >> 4);

        /* Tiny deterministic flutter for organic motion. */
        uint8_t flutter = (uint8_t)(((anim_env->time >> 6) + i * 17) & 7);
        ax += (int16_t)flutter - 3;
        ay += 3 - (int16_t)((flutter + i) & 7);

        /* Soft edge avoidance keeps birds inside the panel. */
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
        uint16_t edge_dist = (uint16_t)lx;
        uint16_t right_dist = cached_max_x - (uint16_t)lx;
        uint16_t bottom_dist = cached_max_y - (uint16_t)ly;
        uint16_t edge_scale = 255;

        for (int i = 0; i < BIRD_COUNT; i++) {
            int16_t dx = (int16_t)(birds[i].x >> 8) - lx;
            int16_t dy = (int16_t)(birds[i].y >> 8) - ly;
            int32_t dist_sq = (int32_t)dx * dx + (int32_t)dy * dy;
            if (dist_sq < RENDER_RADIUS_SQ) {
                density += (uint16_t)(72 - (dist_sq >> 2));
            }
        }

        if ((uint16_t)ly < edge_dist) edge_dist = (uint16_t)ly;
        if (right_dist < edge_dist) edge_dist = right_dist;
        if (bottom_dist < edge_dist) edge_dist = bottom_dist;
        if (edge_dist < EDGE_FADE_MARGIN) {
            edge_scale = 96 + ((edge_dist * 160) >> 5);
        }

        if (density > MAX_DENSITY) density = MAX_DENSITY;
        density = (density * edge_scale) >> 8;
        HSV hsv = {
            .h = (uint8_t)(145 + (density >> 4)),
            .s = 90,
            .v = (uint8_t)density,
        };
        anim_env->set_color_hsv(led, hsv);
    }

    return false;
}
