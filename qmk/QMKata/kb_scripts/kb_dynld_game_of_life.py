dynld_animation_c = '''
#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

/* Grid dimensions: 2 rows reserved, 4 rows active (matches Q3 Max physical layout) */
#define LIFE_ROWS 4
#define LIFE_COLS 15
#define LIFE_CELLS (LIFE_ROWS * LIFE_COLS)
#define N_BYTES    ((LIFE_CELLS + 7) / 8)   /* 8 bytes for 60-bit grid */

/* buf layout: bytes 0..N_BYTES-1 = current grid, N_BYTES..2*N_BYTES-1 = next grid */
#define GRID_OFF    0
#define NEXT_OFF    N_BYTES

/* Bit operations on the packed grid stored in buf[] */
static inline bool grid_get(uint8_t *buf, uint8_t row, uint8_t col) {{
    uint8_t idx = row * LIFE_COLS + col;
    return (buf[idx / 8] >> (idx % 8)) & 1;
}}

static inline void grid_set(uint8_t *buf, uint8_t row, uint8_t col, bool alive) {{
    uint8_t idx = row * LIFE_COLS + col;
    if (alive)
        buf[idx / 8] |= (1 << (idx % 8));
    else
        buf[idx / 8] &= ~(1 << (idx % 8));
}}

/* Count live neighbors (toroidal wrap) */
static uint8_t count_neighbors(uint8_t *buf, uint8_t row, uint8_t col) {{
    uint8_t n = 0;
    for (int dr = -1; dr <= 1; dr++) {{
        for (int dc = -1; dc <= 1; dc++) {{
            if (dr == 0 && dc == 0) continue;
            uint8_t r = (row + dr + LIFE_ROWS) % LIFE_ROWS;
            uint8_t c = (col + dc + LIFE_COLS) % LIFE_COLS;
            if (grid_get(buf, r, c)) n++;
        }}
    }}
    return n;
}}

/* Compute one generation from current grid into next grid */
static void life_step(uint8_t *buf) {{
    for (uint8_t row = 0; row < LIFE_ROWS; row++) {{
        for (uint8_t col = 0; col < LIFE_COLS; col++) {{
            uint8_t n = count_neighbors(buf + GRID_OFF, row, col);
            bool alive = grid_get(buf + GRID_OFF, row, col);
            bool next;
            if (alive) {{
                next = (n == 2 || n == 3);
            }} else {{
                next = (n == 3);
            }}
            grid_set(buf + NEXT_OFF, row, col, next);
        }}
    }}
}}

/* Check if the grid has any live cells (avoids black display on all-dead) */
static bool grid_has_life(uint8_t *buf) {{
    for (uint8_t i = 0; i < N_BYTES; i++) {{
        if (buf[i] != 0) return true;
    }}
    return false;
}}

/* Render current grid state to LEDs.
 * Dims all LEDs first, then lights only the grid cells. Cells at
 * matrix positions with no LED (matrix_co == 255) are skipped. */
static void life_render(dynld_custom_animation_env_t *anim_env, uint8_t *buf) {{
    uint8_t led_count = RGB_MATRIX_LED_COUNT;

    /* Dim all LEDs so non-grid areas aren't dark */
    for (uint8_t i = 0; i < led_count; i++) {{
        anim_env->set_color(i, 1, 1, 1);
    }}

    /* Light grid cells */
    for (uint8_t gr = 0; gr < LIFE_ROWS; gr++) {{
        for (uint8_t col = 0; col < LIFE_COLS; col++) {{
            uint8_t row = gr + 2;  /* skip top 2 matrix rows (Esc, F-keys) */
            uint8_t led = anim_env->led_config->matrix_co[row][col];
            if (led == 255) continue;

            bool alive = grid_get(buf + GRID_OFF, gr, col);
            if (alive) {{
                anim_env->set_color(led, 0, 255, 0);
            }} else {{
                anim_env->set_color(led, 4, 4, 4);
            }}
        }}
    }}
}}

/* Seed with a random pattern */
static void life_seed(uint8_t *buf, uint32_t seed) {{
    uint8_t s = seed & 0xFF;
    for (uint8_t row = 0; row < LIFE_ROWS; row++) {{
        for (uint8_t col = 0; col < LIFE_COLS; col++) {{
            s = s * 1103515245 + 12345;
            bool alive = ((s >> 16) & 3) == 0;  /* ~25% density */
            grid_set(buf, row, col, alive);
        }}
    }}
    /* Copy to next buffer so initial render shows the seed */
    for (uint8_t i = 0; i < N_BYTES; i++)
        buf[NEXT_OFF + i] = buf[GRID_OFF + i];
}}

bool effect_runner_dx_dy_dist(dynld_custom_animation_env_t *anim_env, effect_params_t* params) {{
    uint8_t *buf = anim_env->buf;

    /* Speed controls generation rate: 0=slowest, 255=fastest.
     * Map to approximate ms between generations (4ms to 1s range). */
    uint8_t speed = anim_env->rgb_config->speed;
    uint16_t interval = 1024 / (speed + 1);  /* 4ms at max → 1024ms at min */
    uint32_t elapsed = anim_env->time;

    /* Seed on first call if grid is empty */
    if (!grid_has_life(buf + GRID_OFF)) {{
        life_seed(buf, anim_env->time);
        buf[2*N_BYTES] = 0;
        buf[2*N_BYTES+1] = 0;
    }}

    /* Step when enough time has elapsed */
    uint16_t last_step = (buf[2*N_BYTES+1] << 8) | buf[2*N_BYTES];
    if (elapsed - last_step >= interval) {{
        life_step(buf);

        /* Copy next → current */
        for (uint8_t i = 0; i < N_BYTES; i++)
            buf[GRID_OFF + i] = buf[NEXT_OFF + i];

        buf[2*N_BYTES]   = elapsed & 0xFF;
        buf[2*N_BYTES+1] = (elapsed >> 8) & 0xFF;

        /* Re-seed if all cells died */
        if (!grid_has_life(buf + GRID_OFF)) {{
            life_seed(buf, anim_env->time);
        }}
    }}

    life_render(anim_env, buf);
    return true;
}}
'''

if True:
    c_code = dynld_animation_c.format()
    print("code:", c_code)
