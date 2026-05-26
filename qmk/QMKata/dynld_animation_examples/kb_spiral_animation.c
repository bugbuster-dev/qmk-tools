/* Band Spiral SAT — RGB matrix dynld animation.
 *
 * Original animation from kb_scripts/kb_dynld_animation.py,
 * converted to standalone C source for build_dynld().
 *
 * Hue cycles slowly via hsv_h, saturation spirals from center.
 * Built with ModuleBuild pipeline for multi-function support.
 */

#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

static inline uint8_t _scale8(uint16_t i, uint8_t scale) {
    return ((uint16_t)i * (uint16_t)(scale)) >> 8;
}

static inline uint8_t _scale16by8(uint16_t i, uint8_t scale) {
    return (i * (1 + ((uint16_t)scale))) >> 8;
}

static inline HSV spiral_math(dynld_custom_animation_env_t *env, HSV hsv,
                               int16_t dx, int16_t dy, uint8_t dist, uint8_t time) {
    hsv.s = _scale8(hsv.s + dist - time - env->math_funs->atan2_8(dy, dx), hsv.s);
    hsv.h = 85;  /* fixed hue — green ~120 on HSV wheel, 85 = blue-green */
    hsv.v = hsv.s;
    return hsv;
}

bool effect_runner_dx_dy_dist(dynld_custom_animation_env_t *anim_env,
                               effect_params_t *params) {
    const led_point_t k_rgb_matrix_center = { 112, 32 };
    uint8_t led_max = RGB_MATRIX_LED_COUNT;
    uint8_t time = _scale16by8(anim_env->time, anim_env->rgb_config->speed >> 1);

    for (int i = 0; i < led_max; i++) {
        int16_t dx = anim_env->led_config->point[i].x - k_rgb_matrix_center.x;
        int16_t dy = anim_env->led_config->point[i].y - k_rgb_matrix_center.y;
        uint8_t dist = anim_env->math_funs->sqrt16(dx * dx + dy * dy);

        HSV hsv = spiral_math(anim_env, anim_env->rgb_config->hsv, dx, dy, dist, time);
        anim_env->set_color_hsv(i, hsv);
    }
    return false;
}
