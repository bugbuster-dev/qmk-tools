
class KeychronQ3Max:
    NAME = "keychron q3 max"
    VID = 0x3434
    PID = 0x0830
    PORT_TYPE = "rawhid"

    RGB_MAXTRIX_W = 17
    RGB_MAXTRIX_H = 6
    NUM_RGB_LEDS = 87

    DEFAULT_LAYER = { 'm':0, 'w':2 }
    NUM_LAYERS = 8
    #---------------------------------------------------------------------------

    def __init__(self):
        pass

    @staticmethod
    def name():
        return KeychronQ3Max.NAME

    @staticmethod
    def vid_pid():
        return (KeychronQ3Max.VID, KeychronQ3Max.PID)

    @staticmethod
    def rgb_matrix_size():
        return (KeychronQ3Max.RGB_MAXTRIX_W, KeychronQ3Max.RGB_MAXTRIX_H)

    @staticmethod
    def num_rgb_leds():
        return KeychronQ3Max.NUM_RGB_LEDS

    @staticmethod
    def default_layer(mode):
        layer = KeychronQ3Max.DEFAULT_LAYER[mode.lower()]
        return layer

    @staticmethod
    def num_layers():
        return KeychronQ3Max.NUM_LAYERS

    # pixel position to (rgb) led index
    @staticmethod
    def xy_to_rgb_index(x, y):
        __ = -1
        xy_to_led = [
        [  0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, __, 13, 14, 15 ],
        [ 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32 ],
        [ 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49 ],
        [ 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 62, __, __, __ ],
        [ 63, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 74, __, 75, __ ],
        [ 76, 77, 78, 79, 79, 79, 79, 79, 79, 79, 80, 81, 82, 83, 84, 85, 86 ],
        ]
        #print(f"xy_to_led[{y}][{x}] = {xy_to_led[y][x]}")
        try:
            return xy_to_led[y][x]
        except:
            return -1

