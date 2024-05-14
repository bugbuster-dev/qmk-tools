
class NuphyAir96V2:
    NAME    = "nuphy air96 v2"
    VID     = 0x19f5
    PID     = 0x3265
    MCU     = "STM32F072","cortex-m0","le32"

    RGB_MAXTRIX_W = 19
    RGB_MAXTRIX_H = 6
    NUM_RGB_LEDS = 110
    RGB_MAX_REFRESH = 25

    DEFAULT_LAYER = { 'm':0, 'w':2 }
    NUM_LAYERS = 8
    #---------------------------------------------------------------------------
    KEY_LAYOUT = { # todo bb
        'win': [
        ['esc'      , 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12', 'volume mute', 'print screen', 'scroll lock', 'pause'],
        ['`'        ,  '1',  '2',  '3',  '4',  '5',  '6',  '7',  '8',  '9',   '0',   '-',   '=', 'backspace', 'morse', 'home', 'page up'],
        ['tab'      ,  'q',  'w',  'e',  'r',  't',  'y',  'u',  'i',   'o',   'p',   '[', ']', '\\', 'delete', 'end', 'page down'],
        ['caps lock' ,  'a',  's',  'd',  'f',  'g',  'h',  'j',  'k',   'l',   ';',  '\'', '', 'enter', '', ''],
        ['left shift',   '',  'z',  'x',  'c',  'v',  'b',  'n',  'm',   ',',   '.',   '/', '', 'right shift', '', 'up', ''],
        ['left ctrl', 'left windows', 'left menu', '', '', '', 'space', '', '', '', 'right menu', 'right windows', 'fn', 'ctrl', 'left', 'down', 'right']]
    }

    def __init__(self):
        pass

    @staticmethod
    def name():
        return NuphyAir96V2.NAME

    @staticmethod
    def vid_pid():
        return (NuphyAir96V2.VID, NuphyAir96V2.PID)

    @staticmethod
    def mcu():
        return NuphyAir96V2.MCU

    @staticmethod
    def matrix_size():
        return (NuphyAir96V2.MAXTRIX_W, NuphyAir96V2.MAXTRIX_H)

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

    class KeybConfiguration_v0_1:
        CONFIG_DEBUG = {
            1: "enable",
            2: "matrix",
            3: "keyboard",
            4: "mouse",
        }
        CONFIG_DEBUG_USER = {
            1: "firmata",
            2: "stats",
            3: "user animation",
        }
        CONFIG_RGB = {
            1: "enable",
            2: "mode",
            3: "hsv_h",
            4: "hsv_s",
            5: "hsv_v",
            6: "speed",
            7: "flags",
        }
        CONFIG_KEYMAP = {
            1: "swap_control_capslock",
            2: "capslock_to_control",
            3: "swap_lalt_lgui",
            4: "swap_ralt_rgui",
            5: "no_gui",
            6: "swap_grave_esc",
            7: "swap_backslash_backspace",
            8: "nkro",
            9: "swap_lctl_lgui",
            10: "swap_rctl_rgui",
            11: "oneshot_enable",
            12: "swap_escape_capslock",
            13: "autocorrect_enable",
        }
        CONFIG_KEYMAP_LAYOUT = {
            1: "keymap layout",
        }
        CONFIG_DEBOUNCE = {
            1: "debounce",
        }
        CONFIG_DEVEL = {
            1: "pub_keypress",
            2: "process_keypress",
        }
        CONFIG = {
            1: ("debug", CONFIG_DEBUG),
            2: ("debug user", CONFIG_DEBUG_USER),
            3: ("rgb", CONFIG_RGB),
            4: ("keymap", CONFIG_KEYMAP),
            5: ("keymap layout", CONFIG_KEYMAP_LAYOUT),
            6: ("debounce", CONFIG_DEBOUNCE),
            7: ("devel", CONFIG_DEVEL),
        }
        CONFIG_FLAGS = {
            1: "flash",
            2: "readonly",
        }
        TYPES = { #todo move to common
            1: "bit",
            2: "uint8",
            3: "uint16",
            4: "uint32",
            5: "uint64",
            6: "float",
            0x80: "array",
            "bit":      1,
            "uint8":    2,
            "uint16":   3,
            "uint32":   4,
            "uint64":   5,
            "float":    6,
            "array":    0x80,
        }

        @staticmethod
        def config_name(config_id):
            try:
                return NuphyAir96V2.KeybConfiguration_v0_1.CONFIG[config_id][0]
            except:
                return "unknown"

        @staticmethod
        def config_field_name(config_id, field_id):
            try:
                return NuphyAir96V2.KeybConfiguration_v0_1.CONFIG[config_id][1][field_id]
            except:
                return "unknown"

        @staticmethod
        def config_field_type(field_type):
            try:
                if field_type & 0x80:
                    item_type = field_type & 0x7F
                    return 'array:' + NuphyAir96V2.KeybConfiguration_v0_1.TYPES[item_type]
                else:
                    return NuphyAir96V2.KeybConfiguration_v0_1.TYPES[field_type]
            except:
                return "unknown"

        @staticmethod
        def print_config_layout(config_id, config_fields):
            config_name = NuphyAir96V2.KeybConfiguration_v0_1.config_name(config_id)
            print(f"config[{config_id}]: {config_name}")
            for field_id, field in config_fields.items():
                field_name = NuphyAir96V2.KeybConfiguration_v0_1.config_field_name(config_id, field_id)
                field_type = NuphyAir96V2.KeybConfiguration_v0_1.config_field_type(field[0])
                try:
                    field_offset = field[1]
                except:
                    field_offset = -1
                try:
                    field_size = field[2]
                except:
                    field_size = -1
                print(f"  field:{field_name}, "
                        f"type:{field_type}, "
                        f"offset:{field_offset}, "
                        f"size:{field_size}")

        @staticmethod
        def keyb_config_model(model, config_id, config_fields):
            from PySide6.QtGui import Qt, QStandardItemModel, QStandardItem

            def create_item(text, editable=False):
                item = QStandardItem(str(text))
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                return item

            def add_config_to_model(model, config_id, config_fields):
                config_name = NuphyAir96V2.KeybConfiguration_v0_1.config_name(config_id)
                config_item = create_item(config_name)
                for field_id, field_info in config_fields.items():
                    #print(f"field_id:{field_id}, field_info:{field_info}")
                    try:
                        field_name = create_item(NuphyAir96V2.KeybConfiguration_v0_1.config_field_name(config_id, field_id))
                        field_type = create_item(NuphyAir96V2.KeybConfiguration_v0_1.config_field_type(field_info[0]))
                        field_size = create_item(field_info[2])
                        field_flags = field_info[3]
                        if field_flags & 0x2:
                            editable = False
                        else:
                            editable = True
                        field_value = create_item("", editable=editable)
                        field = [field_name, field_type, field_size, field_value]
                        config_item.appendRow(field)
                    except:
                        pass
                model.appendRow(config_item)

            if model is None:
                model = QStandardItemModel()
                model.setHorizontalHeaderLabels(["field", "type", "size", "value"])

            add_config_to_model(model, config_id, config_fields)
            return model

    @staticmethod
    def keyb_config():
        return NuphyAir96V2.KeybConfiguration_v0_1
