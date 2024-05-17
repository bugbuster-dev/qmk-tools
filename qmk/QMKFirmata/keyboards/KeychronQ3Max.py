class KeychronQ3Max:
    NAME    = "keychron q3 max"
    VID     = 0x3434
    PID     = 0x0830
    MCU     = "STM32F402","cortex-m4","le32"
    PORT_TYPE   = "rawhid"

    MAXTRIX_W       = 17
    MAXTRIX_H       = 6
    RGB_MAXTRIX_W   = 17
    RGB_MAXTRIX_H   = 6
    NUM_RGB_LEDS    = 87
    RGB_MAX_REFRESH = 25

    DEFAULT_LAYER   = { 'm':0, 'w':2 }
    NUM_LAYERS      = 8
    #---------------------------------------------------------------------------
    KEY_LAYOUT = {
        'win': [
        ['esc'      , 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12', 'volume mute', 'print screen', 'scroll lock', 'pause'],
        ['`'        ,  '1',  '2',  '3',  '4',  '5',  '6',  '7',  '8',  '9',   '0',   '-',   '=', 'backspace', 'morse', 'home', 'page up'],
        ['tab'      ,  'q',  'w',  'e',  'r',  't',  'y',  'u',  'i',   'o',   'p',   '[', ']', '\\', 'delete', 'end', 'page down'],
        ['caps lock' ,  'a',  's',  'd',  'f',  'g',  'h',  'j',  'k',   'l',   ';',  '\'', '', 'enter', '', ''],
        ['left shift',   '',  'z',  'x',  'c',  'v',  'b',  'n',  'm',   ',',   '.',   '/', '', 'right shift', '', 'up', ''],
        ['left ctrl', 'left windows', 'left menu', '', '', '', 'space', '', '', '', 'right menu', 'right windows', 'fn', 'ctrl', 'left', 'down', 'right']]
    }

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
    def mcu():
        return KeychronQ3Max.MCU

    @staticmethod
    def matrix_size():
        return (KeychronQ3Max.MAXTRIX_W, KeychronQ3Max.MAXTRIX_H)

    @staticmethod
    def rgb_matrix_size():
        return (KeychronQ3Max.RGB_MAXTRIX_W, KeychronQ3Max.RGB_MAXTRIX_H)

    @staticmethod
    def rgb_max_refresh():
        return KeychronQ3Max.RGB_MAX_REFRESH

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

    class KeybStruct:
        TYPES = {
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
        FLAGS = {
            1: "readonly",
            "readonly": 1,
        }

        @staticmethod
        def struct_name(_name_dict, _id):
            try:
                return _name_dict[_id][0]
            except:
                return "unknown"
        @staticmethod
        def struct_field_name(_name_dict, config_id, field_id):
            try:
                return _name_dict[config_id][1][field_id]
            except:
                return "unknown"

        @staticmethod
        def struct_field_type(field_type):
            try:
                if field_type & 0x80:
                    item_type = field_type & 0x7F
                    return 'array:' + KeychronQ3Max.KeybStruct.TYPES[item_type]
                else:
                    return KeychronQ3Max.KeybStruct.TYPES[field_type]
            except:
                return "unknown"

        @staticmethod
        def print_struct(derived_class, struct_id, struct_fields):
            config_name = derived_class.struct_name(struct_id)
            print(f"struct[{struct_id}]: {config_name}")
            for field_id, field in struct_fields.items():
                field_name = derived_class.struct_field_name(struct_id, field_id)
                field_type = derived_class.struct_field_type(field[0])
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
        def struct_model(model, derived_class, config_id, config_fields):
            from PySide6.QtGui import Qt, QStandardItemModel, QStandardItem

            def create_item(text, editable=False):
                item = QStandardItem(str(text))
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                return item

            def add_config_to_model(model, config_id, config_fields):
                config_name = derived_class.struct_name(config_id)
                config_item = create_item(config_name)
                for field_id, field_info in config_fields.items():
                    #print(f"field_id:{field_id}, field_info:{field_info}")
                    try:
                        field_name = create_item(derived_class.struct_field_name(config_id, field_id))
                        field_type = create_item(derived_class.struct_field_type(field_info[0]))
                        field_size = create_item(field_info[2])
                        field_flags = field_info[3]
                        if field_flags & KeychronQ3Max.KeybStruct.FLAGS["readonly"]:
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

        @staticmethod
        def struct_name(config_id):
            return KeychronQ3Max.KeybStruct.struct_name(KeychronQ3Max.KeybConfiguration_v0_1.CONFIG, config_id)

        @staticmethod
        def struct_field_name(config_id, field_id):
            return KeychronQ3Max.KeybStruct.struct_field_name(KeychronQ3Max.KeybConfiguration_v0_1.CONFIG, config_id, field_id)

        @staticmethod
        def struct_field_type(field_type):
            return KeychronQ3Max.KeybStruct.struct_field_type(field_type)

        @staticmethod
        def print_struct(struct_id, struct_fields):
            KeychronQ3Max.KeybStruct.print_struct(KeychronQ3Max.KeybConfiguration_v0_1, struct_id, struct_fields)

        @staticmethod
        def struct_model(model, config_id, config_fields):
            return KeychronQ3Max.KeybStruct.struct_model(model, KeychronQ3Max.KeybConfiguration_v0_1, config_id, config_fields)

    class KeybStatus_v0_1:
        STATUS_BATTERY = {
            1: "level",
            2: "charging",
        }
        STATUS_DIP_SWITCH = {
            1: "mac/win",
        }
        STATUS_MATRIX = {
            1: "raw matrix",
        }
        STATUS = {
            1: ("battery", STATUS_BATTERY),
            2: ("dip switch", STATUS_DIP_SWITCH),
            3: ("matrix", STATUS_MATRIX),
        }

        @staticmethod
        def struct_name(config_id):
            return KeychronQ3Max.KeybStruct.struct_name(KeychronQ3Max.KeybStatus_v0_1.STATUS, config_id)

        @staticmethod
        def struct_field_name(config_id, field_id):
            return KeychronQ3Max.KeybStruct.struct_field_name(KeychronQ3Max.KeybStatus_v0_1.STATUS, config_id, field_id)

        @staticmethod
        def struct_field_type(field_type):
            return KeychronQ3Max.KeybStruct.struct_field_type(field_type)

        @staticmethod
        def print_struct(struct_id, struct_fields):
            KeychronQ3Max.KeybStruct.print_struct(KeychronQ3Max.KeybStatus_v0_1, struct_id, struct_fields)

        @staticmethod
        def struct_model(model, config_id, config_fields):
            return KeychronQ3Max.KeybStruct.struct_model(model, KeychronQ3Max.KeybStatus_v0_1, config_id, config_fields)

    @staticmethod
    def keyb_config():
        return KeychronQ3Max.KeybConfiguration_v0_1

    @staticmethod
    def keyb_status():
        return KeychronQ3Max.KeybStatus_v0_1
