#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define BIRD_COUNT 24
#define MAX_SPEED_MIN_Q8 80    /* slow extreme (~0.31 px/frame), at the split fully open */
#define MAX_SPEED_MAX_Q8 220   /* fast extreme (~0.86 px/frame), at the merge moment */
#define EDGE_MARGIN_Q8 (24 << 8)
#define EDGE_FORCE_Q8 18
#define MIGRATE_MARGIN_Q8 (32 << 8)
#define CRUISE_Q8 64
#define EDGE_FADE_MARGIN 32
#define MAX_DENSITY 220
#define PERCEPTION_RADIUS 44
#define PERCEPTION_RADIUS_SQ (PERCEPTION_RADIUS * PERCEPTION_RADIUS)
#define SEPARATION_RADIUS_Q8 (12 << 8)
#define SEPARATION_RADIUS (SEPARATION_RADIUS_Q8 >> 8)
#define SEPARATION_RADIUS_SQ (SEPARATION_RADIUS * SEPARATION_RADIUS)
#define RENDER_RADIUS 18
#define RENDER_RADIUS_SQ (RENDER_RADIUS * RENDER_RADIUS)
/* Fission-fusion dance: the two sub-flocks aim at center +/- a breathing
 * offset along a slowly rotating axis. Because the offset is bounded, the
 * split distance is bounded too — the flocks always stay close enough to
 * reconnect and then merge again when the offset breathes back to zero. */
#define SPLIT_OFFSET_SHIFT 6   /* scales oscillator product down to px */
#define SPLIT_OFFSET_MAX 32    /* px; caps how far the flocks separate */
#define VERTICAL_OFFSET_MAX 0  /* px; keep split horizontal on six-row matrix */
#define SPLIT_STEER_SHIFT 2    /* how firmly birds seek their sub-flock */
#define MIDLINE_RECENTER_SHIFT 3

typedef struct {
    /* Q8 coordinates are non-negative and fit in uint16_t on the Q3 Max.
     * Keeping them compact prevents static state from overrunning dynld RAM. */
    uint16_t x;
    uint16_t y;
    int16_t vx;
    int16_t vy;
} bird_t;

static bird_t birds[BIRD_COUNT];
static uint16_t cached_max_x = 0;
static uint16_t cached_max_y = 0;
static int8_t travel_dir = 0;
static bool initialized = false;

static inline int16_t clamp_speed(int16_t v, int16_t cap) {
    if (v >  cap) return  cap;
    if (v < -cap) return -cap;
    return v;
}

static inline int16_t clamp_offset(int16_t v) {
    if (v > SPLIT_OFFSET_MAX) return SPLIT_OFFSET_MAX;
    if (v < -SPLIT_OFFSET_MAX) return -SPLIT_OFFSET_MAX;
    return v;
}

/* clamp_vertical_offset is unnecessary while VERTICAL_OFFSET_MAX == 0
 * (off_y is always 0). Re-add it if you ever raise the vertical range. */

/* Integer triangle wave approximating a sine over 0..255 -> ~[-128,128].
 * Drives the dance oscillator; no float / LUT needed. */
static inline int16_t tri8(uint8_t p) {
    if (p < 64) return (int16_t)(p * 2);
    if (p < 192) return (int16_t)(128 - (p - 64) * 2);
    return (int16_t)(-128 + (p - 192) * 2);
}

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env, effect_params_t *params) {
    if (params->init || !initialized) {
        /* cached_max_x/y start at 0 (.bss / explicit reset on re-init); the
         * loop below only widens them, so re-entering with the same physical
         * layout is idempotent. */
        for (int led = 0; led < RGB_MATRIX_LED_COUNT; led++) {
            uint8_t lx = anim_env->led_config->point[led].x;
            uint8_t ly = anim_env->led_config->point[led].y;
            if (lx > cached_max_x) cached_max_x = lx;
            if (ly > cached_max_y) cached_max_y = ly;
        }

        uint32_t seed = anim_env->time | 1u;
        for (int i = 0; i < BIRD_COUNT; i++) {
            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            birds[i].x = (uint16_t)(anim_env->math_funs->mod((int)(seed >> 8), cached_max_x + 1) << 8);

            seed ^= seed << 13;
            seed ^= seed >> 17;
            seed ^= seed << 5;
            birds[i].y = (uint16_t)(anim_env->math_funs->mod((int)(seed >> 8), cached_max_y + 1) << 8);

            birds[i].vx = CRUISE_Q8;
            birds[i].vy = (int16_t)((((i >> 2) & 3) - 1) * 16);
        }
        travel_dir = 1;
        initialized = true;
    }

    /* Advance the simulation once per frame, not once per LED chunk.
     * The QMK matrix task calls this function several times per frame
     * (params->iter goes 0..N) to slice rendering across ticks; the
     * boids step must only fire when iter==0 so cost stays O(N^2) per
     * frame instead of O(N^2 * chunks). */
    if (params->iter == 0) {
    int32_t bound_x_q8 = (int32_t)cached_max_x << 8;
    int32_t bound_y_q8 = (int32_t)cached_max_y << 8;

    /* Global flock center (Q8). Used for migration and as the pivot the two
     * sub-flocks split around. */
    int32_t center_x = 0, center_y = 0;
    for (int i = 0; i < BIRD_COUNT; i++) {
        center_x += birds[i].x;
        center_y += birds[i].y;
    }
    center_x /= BIRD_COUNT;
    center_y /= BIRD_COUNT;
    int16_t center_xp = (int16_t)(center_x >> 8);
    int16_t mid_y = (int16_t)(cached_max_y >> 1);

    /* Migration: reverse cruise direction when the whole flock nears a side,
     * so the dancing mass also drifts across the panel. */
    if (center_x > bound_x_q8 - MIGRATE_MARGIN_Q8) travel_dir = -1;
    else if (center_x < MIGRATE_MARGIN_Q8) travel_dir = 1;
    int16_t cruise_vx = (int16_t)(travel_dir * CRUISE_Q8);

    /* Dance oscillators. sep_osc breathes the split open (>0) and shut (<=0);
     * axis_x/axis_y slowly rotate the split direction. The per-team target
     * offset is bounded so the flocks can never fully separate. */
    uint8_t ph  = (uint8_t)((anim_env->time >> 6) & 0xFF);
    uint8_t aph = (uint8_t)((anim_env->time >> 7) & 0xFF);
    int16_t sep_osc = tri8(ph);
    int16_t axis_x  = tri8(aph);
    int16_t split = sep_osc > 0 ? sep_osc : 0;
    int16_t off_x = clamp_offset((int16_t)((split * axis_x) >> SPLIT_OFFSET_SHIFT));
    /* Vertical split is disabled (VERTICAL_OFFSET_MAX == 0) to keep the
     * flock visible on all six rows; re-introduce a tri8(aph + 64) axis
     * and clamp here if you raise that limit. */
    int16_t off_y = 0;

    /* Per-frame top-speed cap breathes with the dance: |sep_osc| is ~128
     * at the split extremes and 0 at the merge crossing. Invert it so the
     * cap is highest at the merge moment and lowest while fully separated. */
    int16_t abs_sep = sep_osc >= 0 ? sep_osc : (int16_t)-sep_osc;
    uint8_t merge_phase = (uint8_t)(128 - abs_sep);
    int16_t cur_max_speed_q8 = (int16_t)(MAX_SPEED_MIN_Q8 +
        (((uint32_t)merge_phase *
          (MAX_SPEED_MAX_Q8 - MAX_SPEED_MIN_Q8)) >> 7));

    for (int i = 0; i < BIRD_COUNT; i++) {
        bird_t *b = &birds[i];
        int16_t team = (i & 1) ? 1 : -1;
        int16_t bxp = (int16_t)(b->x >> 8);
        int16_t byp = (int16_t)(b->y >> 8);

        int32_t same_cx = 0, same_cy = 0, same_vx = 0, same_vy = 0;
        int32_t sep_x = 0, sep_y = 0;
        int16_t same_n = 0;

        /* Local neighborhood among same-team birds: cohesion + alignment
         * keep each sub-flock tight. Separation (any neighbor) avoids
         * overlap. This locality gives the murmuration shimmer. */
        for (int j = 0; j < BIRD_COUNT; j++) {
            if (i == j) continue;

            int16_t dx = bxp - (int16_t)(birds[j].x >> 8);
            int16_t dy = byp - (int16_t)(birds[j].y >> 8);
            int32_t dist_sq = (int32_t)dx * dx + (int32_t)dy * dy;
            if (dist_sq >= PERCEPTION_RADIUS_SQ) continue;

            if (((i ^ j) & 1) == 0) {
                same_n++;
                same_cx += (int16_t)(birds[j].x >> 8);
                same_cy += (int16_t)(birds[j].y >> 8);
                same_vx += birds[j].vx;
                same_vy += birds[j].vy;
            }
            if (dist_sq < SEPARATION_RADIUS_SQ) {
                sep_x += dx;
                sep_y += dy;
            }
        }

        int16_t coh_x = 0, coh_y = 0;
        int16_t ali_x = 0, ali_y = 0;
        if (same_n > 0) {
            coh_x = (int16_t)(anim_env->math_funs->div((int)same_cx, same_n) - bxp);
            coh_y = (int16_t)(anim_env->math_funs->div((int)same_cy, same_n) - byp);
            ali_x = (int16_t)(anim_env->math_funs->div((int)same_vx, same_n) - b->vx);
            ali_y = (int16_t)(anim_env->math_funs->div((int)same_vy, same_n) - b->vy);
        }

        /* Each team seeks center +/- the breathing offset: the two flocks
         * pull apart as the offset opens and rejoin as it closes. */
        int16_t target_x = center_xp + team * off_x;
        int16_t target_y = mid_y + team * off_y;
        int16_t dance_ax = (int16_t)((target_x - bxp) >> SPLIT_STEER_SHIFT);
        int16_t dance_ay = (int16_t)((target_y - byp) >> SPLIT_STEER_SHIFT);

        int16_t ax = (int16_t)(sep_x << 3) + (ali_x >> 2) + (coh_x >> 3) +
                     ((cruise_vx - b->vx) >> 4) + dance_ax;
        int16_t ay = (int16_t)(sep_y << 3) + (ali_y >> 2) + (coh_y >> 3) +
                     ((-b->vy) >> 4) + ((mid_y - byp) >> 2) + dance_ay;

        uint8_t flutter = (uint8_t)(((anim_env->time >> 6) + i * 17) & 7);
        ax += (int16_t)flutter - 3;
        ay += 3 - (int16_t)((flutter + i) & 7);

        if (b->x < EDGE_MARGIN_Q8) ax += EDGE_FORCE_Q8;
        if (b->x > bound_x_q8 - EDGE_MARGIN_Q8) ax -= EDGE_FORCE_Q8;
        if (b->y < EDGE_MARGIN_Q8) ay += EDGE_FORCE_Q8;
        if (b->y > bound_y_q8 - EDGE_MARGIN_Q8) ay -= EDGE_FORCE_Q8;

        b->vx = clamp_speed(b->vx + ax, cur_max_speed_q8);
        b->vy = clamp_speed(b->vy + ay, cur_max_speed_q8);

        int32_t next_x = (int32_t)b->x + b->vx;
        int32_t next_y = (int32_t)b->y + b->vy;
        next_y += (((int32_t)mid_y << 8) - next_y) >> MIDLINE_RECENTER_SHIFT;

        if (next_x < 0) {
            next_x = 0;
            if (b->vx < 0) b->vx = -b->vx >> 1;
        } else if (next_x > bound_x_q8) {
            next_x = bound_x_q8;
            if (b->vx > 0) b->vx = -b->vx >> 1;
        }

        if (next_y < 0) {
            next_y = 0;
            if (b->vy < 0) b->vy = -b->vy >> 1;
        } else if (next_y > bound_y_q8) {
            next_y = bound_y_q8;
            if (b->vy > 0) b->vy = -b->vy >> 1;
        }

        b->x = (uint16_t)next_x;
        b->y = (uint16_t)next_y;
    }
    }

    for (int led = 0; led < RGB_MATRIX_LED_COUNT; led++) {
        /* Respect the user's LED flag mask: skip LEDs whose flags don't
         * overlap params->flags (e.g. underglow/indicators when only
         * keylight is enabled), matching the convention of QMK's stock
         * effects (see RGB_MATRIX_TEST_LED_FLAGS in rgb_matrix.h). */
        if (!(anim_env->led_config->flags[led] & params->flags)) continue;

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
                int16_t contrib = (int16_t)(72 - (dist_sq >> 2));
                if (contrib > 0) density += (uint16_t)contrib;
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
        /* Scale brightness by the user's RGB matrix value so the
         * brightness slider actually affects this effect. */
        density = (density * anim_env->rgb_config->hsv.v) >> 8;
        HSV hsv = {
            .h = (uint8_t)(145 + (density >> 4)),
            .s = 90,
            .v = (uint8_t)density,
        };
        anim_env->set_color_hsv(led, hsv);
    }

    return false;
}
