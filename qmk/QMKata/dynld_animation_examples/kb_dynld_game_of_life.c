/* Conway's Game of Life dynld animation — ModuleBuild pipeline.
 *
 * 4x15 toroidal grid on matrix rows 2-5. Steps every frame.
 * Reseeds when all cells die (green flash = reseed). */

#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define LIFE_ROWS  4
#define LIFE_COLS  15
#define N_BYTES    (((LIFE_ROWS * LIFE_COLS) + 7) / 8)

static bool grid_get(uint8_t *buf, uint8_t row, uint8_t col) {
    uint8_t idx = row * LIFE_COLS + col;
    return (buf[idx >> 3] >> (idx & 7)) & 1;
}

static void grid_set(uint8_t *buf, uint8_t row, uint8_t col, bool alive) {
    uint8_t idx = row * LIFE_COLS + col;
    if (alive) buf[idx >> 3] |= (1 << (idx & 7));
    else       buf[idx >> 3] &= ~(1 << (idx & 7));
}

static uint8_t count_neighbors(uint8_t *buf, uint8_t row, uint8_t col) {
    uint8_t n = 0;
    for (int dr = -1; dr <= 1; dr++) {
        for (int dc = -1; dc <= 1; dc++) {
            if (dr == 0 && dc == 0) continue;
            uint8_t r = (row + dr + LIFE_ROWS) & 3;
            uint8_t c = (col + dc + LIFE_COLS) % LIFE_COLS;
            if (grid_get(buf, r, c)) n++;
        }
    }
    return n;
}

static bool any_alive(uint8_t *buf) {
    for (uint8_t i = 0; i < N_BYTES; i++)
        if (buf[i] != 0) return true;
    return false;
}

static void life_step(uint8_t *src, uint8_t *dst) {
    for (uint8_t row = 0; row < LIFE_ROWS; row++) {
        for (uint8_t col = 0; col < LIFE_COLS; col++) {
            uint8_t n = count_neighbors(src, row, col);
            bool alive = grid_get(src, row, col);
            bool next = alive ? (n == 2 || n == 3) : (n == 3);
            grid_set(dst, row, col, next);
        }
    }
}

static void life_render(dynld_custom_animation_env_t *anim_env, uint8_t *buf) {
    uint8_t leds = RGB_MATRIX_LED_COUNT;
    for (uint8_t i = 0; i < leds; i++)
        anim_env->set_color(i, 1, 1, 1);

    for (uint8_t gr = 0; gr < LIFE_ROWS; gr++) {
        for (uint8_t col = 0; col < LIFE_COLS; col++) {
            uint8_t led = anim_env->led_config->matrix_co[gr + 2][col];
            if (led == 255) continue;
            bool alive = grid_get(buf, gr, col);
            anim_env->set_color(led, alive ? 0 : 4, alive ? 255 : 4, alive ? 0 : 4);
        }
    }
}

static void life_seed(uint8_t *buf, uint32_t seed) {
    uint8_t s = seed & 0xFF;
    for (uint8_t row = 0; row < LIFE_ROWS; row++)
        for (uint8_t col = 0; col < LIFE_COLS; col++) {
            s = s * 1103515245 + 12345;
            grid_set(buf, row, col, ((s >> 16) & 3) == 0);
        }
}

bool effect_runner_dx_dy_dist(dynld_custom_animation_env_t *anim_env,
                               effect_params_t *params) {
    uint8_t *buf = anim_env->buf;
    uint8_t leds = RGB_MATRIX_LED_COUNT;

    /* One-shot seed */
    if (buf[63] == 0) {
        buf[63] = 1;
        life_seed(buf, anim_env->time);
    }

    /* Step current → next */
    life_step(buf, buf + N_BYTES);

    /* Check if all cells died */
    if (!any_alive(buf + N_BYTES)) {
        /* Flash green briefly = reseed event */
        for (uint8_t i = 0; i < leds; i++)
            anim_env->set_color(i, 0, 255, 0);
        life_seed(buf, anim_env->time);
        for (uint8_t i = 0; i < N_BYTES; i++)
            buf[N_BYTES + i] = buf[i];
        return false;
    }

    /* Copy next → current */
    for (uint8_t i = 0; i < N_BYTES; i++)
        buf[i] = buf[N_BYTES + i];

    life_render(anim_env, buf);
    return false;
}
