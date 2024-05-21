dynld_animation_c = '''

#include "info_config.h" // include generated config file in .build/...
#include "rgb_matrix.h"

#include "dynld_func.h"

static inline uint8_t _scale8(uint16_t i, uint8_t scale ) {{
        return ((uint16_t)i * (uint16_t)(scale) ) >> 8;
}}

static inline uint8_t _scale16by8(uint16_t i, uint8_t scale ) {{
    return (i * (1+((uint16_t)scale))) >> 8;
}}

static inline HSV BAND_SPIRAL_SAT_math(dynld_custom_animation_env_t *anim_env, HSV hsv, int16_t dx, int16_t dy, uint8_t dist, uint8_t time) {{
    hsv.s = _scale8(hsv.s + dist - time - anim_env->math_funs->atan2_8(dy, dx), hsv.s);
    hsv.h = time%256;
    hsv.v = hsv.s;
    return hsv;
}}

bool effect_runner_dx_dy_dist(dynld_custom_animation_env_t *anim_env, effect_params_t* params) {{
    const led_point_t k_rgb_matrix_center = {{ 112, 32 }};
    uint8_t led_min = 0;
    uint8_t led_max = RGB_MATRIX_LED_COUNT;
    uint8_t time = _scale16by8(anim_env->time, anim_env->rgb_config->speed >> 1);

    anim_env->buf[0] = time;
    anim_env->buf[1] = anim_env->rgb_config->speed;

    for (int i = led_min; i < led_max; i++) {{
        int16_t dx   = anim_env->led_config->point[i].x - k_rgb_matrix_center.x;
        int16_t dy   = anim_env->led_config->point[i].y - k_rgb_matrix_center.y;
        uint8_t dist = anim_env->math_funs->sqrt16(dx * dx + dy * dy);

        HSV hsv = BAND_SPIRAL_SAT_math(anim_env, anim_env->rgb_config->hsv, dx, dy, dist, time);
        anim_env->set_color_hsv(i, hsv);
    }}
    return false;
}}
'''

dynld_animation_c_file = dynld_animation_c.format()
print("-"*40)
print(dynld_animation_c_file)
print("-"*40)
with open("exec.c", "w") as f:
    f.write(dynld_animation_c_file)

code = kb.compile("exec.c")
if code:
    #print(f"code:\n{code['elf']}\n{code['bin']}")
    print(f"{code['bin'].hex(' ')}")
    kb.load_fun(0, code['bin'])
