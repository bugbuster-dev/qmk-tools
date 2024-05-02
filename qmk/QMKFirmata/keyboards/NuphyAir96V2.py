
class NuphyAir96V2:
    NAME    = "nuphy air96 v2"
    VID     = 0x19f5
    PID     = 0x3265
    MCU     = "STM32F072","cortex-m0","le32"

    RGB_MAXTRIX_W = 19
    RGB_MAXTRIX_H = 6
    NUM_RGB_LEDS = 110
    RGB_MAX_REFRESH = 5

    DEFAULT_LAYER = { 'm':0, 'w':2 }
    NUM_LAYERS = 8
    #---------------------------------------------------------------------------

    def __init__(self):
        pass

    @staticmethod
    def name():
        return NuphyAir96V2.NAME

    @staticmethod
    def vid_pid():
        return (NuphyAir96V2.VID, NuphyAir96V2.PID)

    @staticmethod
    def rgb_matrix_size():
        return (NuphyAir96V2.RGB_MAXTRIX_W, NuphyAir96V2.RGB_MAXTRIX_H)

    @staticmethod
    def rgb_max_refresh():
        return NuphyAir96V2.RGB_MAX_REFRESH

    @staticmethod
    def num_rgb_leds():
        return NuphyAir96V2.NUM_RGB_LEDS

    @staticmethod
    def default_layer(mode):
        layer = NuphyAir96V2.DEFAULT_LAYER[mode.lower()]
        return layer

    @staticmethod
    def num_layers():
        return NuphyAir96V2.NUM_LAYERS

    # pixel position to (rgb) led index
    @staticmethod
    def xy_to_rgb_index(x, y):
        __ = -1
        xy_to_led = [
        [  0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16, 17, 18 ],
        [ 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 32, 33, 34, 35, 36 ],
        [ 37, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54 ],
        [ 55, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 67, 68, 69, 70, 54 ],
        [ 71, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 82, 83, 84, 85, 86, 87 ],
        [ 88, 89, 90, 90, 91, 91, 91, 91, 91, 91, 92, 93, 94, 95, 96, 97, 98, 99, 87 ],
        ]
        #print(f"xy_to_led[{y}][{x}] = {xy_to_led[y][x]}")
        try:
            return xy_to_led[y][x]
        except:
            return -1
