/* Matrix Rain dynld animation — ModuleBuild pipeline.
 *
 * Falling green rain columns mapped by LED x-coordinate. */

#include "info_config.h"
#include "rgb_matrix.h"
#include "dynld_func.h"

#define MATRIX_COLS            14
#define MATRIX_ROWS            6
#define MATRIX_SPEED           8
#define MATRIX_TRAIL_MIN       3
#define MATRIX_TRAIL_MAX       8
#define MATRIX_GREEN_R         0
#define MATRIX_GREEN_G         255
#define MATRIX_GREEN_B         0
#define MATRIX_HEAD_BRIGHTNESS 255

static uint8_t col_position[MATRIX_COLS];
static uint8_t col_speed[MATRIX_COLS];
static uint8_t col_trail[MATRIX_COLS];
static uint8_t frame_counter;
static uint32_t lcg_seed;
static bool initialized;
