/* Conway's Game of Life dynld animation — ModuleBuild pipeline.
 *
 * 4x15 toroidal grid on matrix rows 2-5.
 * Steps every LIFE_STEP_INTERVAL frames via buf[62] counter.
 * Seeds once via buf[63] flag. Reseeds when all cells die. */

#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

extern void mprintf(const char *fmt, ...);

#define LIFE_ROWS        4
#define LIFE_COLS        14
#define LIFE_ROW_OFFSET  1
#define LIFE_STEP_INTERVAL 200
#define N_BYTES          (((LIFE_ROWS * LIFE_COLS) + 7) / 8)

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

static void life_step(uint8_t *buf) {
    for (uint8_t row = 0; row < LIFE_ROWS; row++) {
        for (uint8_t col = 0; col < LIFE_COLS; col++) {
            uint8_t n = count_neighbors(buf, row, col);
            bool alive = grid_get(buf, row, col);
            bool next = alive ? (n == 2 || n == 3) : (n == 3);
            grid_set(buf + N_BYTES, row, col, next);
        }
    }
}

static bool any_alive(uint8_t *buf) {
    for (uint8_t i = 0; i < N_BYTES; i++)
        if (buf[i] != 0) return true;
    return false;
}

__attribute__((section(".text.entry")))
bool effect_runner_func(dynld_custom_animation_env_t *anim_env,
                                 effect_params_t *params) {
    uint8_t *buf = anim_env->buf;

    if (buf[63] == 0) {
        buf[63] = 1;
        buf[61] = 0;
        uint32_t s = (uint32_t)anim_env->time ^ 0x4B7E1131u;
        for (uint8_t row = 0; row < LIFE_ROWS; row++)
            for (uint8_t col = 0; col < LIFE_COLS; col++) {
                s = s * 1103515245u + 12345u;
                grid_set(buf, row, col, ((s >> 16) & 3) == 0);
            }
    }

    buf[62]++;
    if (buf[62] >= LIFE_STEP_INTERVAL) {
        buf[62] = 0;
        life_step(buf);
        for (uint8_t i = 0; i < N_BYTES; i++)
            buf[i] = buf[N_BYTES + i];

        uint8_t alive_count = 0;
        for (uint8_t i = 0; i < N_BYTES; i++) {
            uint8_t b = buf[i];
            while (b) { alive_count += (b & 1); b >>= 1; }
        }
        mprintf("life: step gen=%d alive=%d\n", buf[61]++, alive_count);

        if (!any_alive(buf)) {
            mprintf("life: all dead, reseeding\n");
            uint32_t s = (uint32_t)anim_env->time ^ 0x4B7E1131u;
            for (uint8_t gr = 0; gr < LIFE_ROWS; gr++)
                for (uint8_t col = 0; col < LIFE_COLS; col++) {
                    s = s * 1103515245u + 12345u;
                    grid_set(buf, gr, col, ((s >> 16) & 3) == 0);
                }
        }
    }

    uint8_t leds = RGB_MATRIX_LED_COUNT;
    for (uint8_t i = 0; i < leds; i++)
        anim_env->set_color(i, 1, 1, 1);

    for (uint8_t gr = 0; gr < LIFE_ROWS; gr++) {
        for (uint8_t col = 0; col < LIFE_COLS; col++) {
            uint8_t led = anim_env->led_config->matrix_co[gr + LIFE_ROW_OFFSET][col];
            if (led == 255) continue;
            bool alive = grid_get(buf, gr, col);
            anim_env->set_color(led, alive ? 0 : 4, alive ? 255 : 4, alive ? 0 : 4);
        }
    }
    return false;
}
