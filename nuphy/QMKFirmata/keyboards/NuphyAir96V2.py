
class NuphyAir96V2:
    NAME = "nuphy air96 v2"
    VID = 0x19f5
    PID = 0x3265

    RGB_MAXTRIX_W = 19
    RGB_MAXTRIX_H = 6
    NUM_RGB_LEDS = 110

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
    def num_rgb_leds():
        return NuphyAir96V2.NUM_RGB_LEDS

    @staticmethod
    def default_layer(mode):
        layer = NuphyAir96V2.DEFAULT_LAYER[mode.lower()]
        return layer

    @staticmethod
    def num_layers():
        return NuphyAir96V2.NUM_LAYERS

    # pixel position to RGB index
    #(0,0)..(18,0)  ->      0..18
    #(0,1)..(18,1)  ->      19..36
    #(0,2)..(18,2)  ->      37..54
    #(0,3)..(18,3)  ->      55..70
    #(0,4)..(18,4)  ->      71..87
    #(0,5)..(18,5)  ->      88..99
    @staticmethod
    def xy_to_rgb_index(x, y):
        if y == 0:
            return min(x,18)
        if y == 1:
            if x >= 14:
                x = x - 1
            return min(x+19,36)
        if y == 2:
            if x < 2:
                x = 0
            else:
                x = x - 1
            return min(x+37,54)
        if y == 3:
            if x < 2:
                x = 0
            elif x == 18:
                return 54
            elif x <= 13:
                x = x - 1
            else:
                x = x - 2
            return min(x+55,70)
        if y == 4:
            if x < 2:
                x = 0
            elif x <= 12:
                x = x - 1
            else:
                x = x - 2
            return min(x+71,87)
        if y == 5:
            if x < 4:
                if x == 3:
                    x = 2
            elif x >= 4 and x <= 9:
                x = 3
            elif x == 18:
                return 87
            else:
                x = x - 6
            return min(x+88,99)

        return 0

