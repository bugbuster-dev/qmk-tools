class KeychronQ3Max:
    NAME = "keychron q3 max"
    VID = 0x3434
    PID = 0x0830
    MCU = "STM32F401xC", "cortex-m4", "le32"
    PORT_TYPE = "rawhid"

    MAXTRIX_W = 17
    MAXTRIX_H = 6
    RGB_MAXTRIX_W = 17
    RGB_MAXTRIX_H = 6
    NUM_RGB_LEDS = 87
    RGB_MAX_REFRESH = 25

    DEFAULT_LAYER = {"m": 0, "w": 2}
    NUM_LAYERS = 8

    # ---------------------------------------------------------------------------
    # Module loader flash layout (must match firmware module_flash.h).
    # The firmware reserves two 16 KB flash sectors (2 and 3 in the MCU's
    # sector table) and divides each into four 4 KB slots, giving 8 slots
    # total. sector_id in the wire protocol is an index into this range
    # (0 = MCU sector 2, 1 = MCU sector 3), not the MCU sector index.
    MODULE_FLASH_FIRST_SECTOR   = 2
    MODULE_FLASH_SECTOR_COUNT   = 2
    MODULE_FLASH_SLOTS_PER_SECTOR = 4
    MODULE_FLASH_SLOT_SIZE      = 0x1000
    # ---------------------------------------------------------------------------
    KEY_LAYOUT = {
        "win": [
            ["esc", "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12", "volume mute", "print screen", "scroll lock", "pause"],
            ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "backspace", "morse", "home", "page up"],
            ["tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\", "delete", "end", "page down"],
            ["caps lock", "a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "", "enter", "", ""],
            ["left shift", "", "z", "x", "c", "v", "b", "n", "m", ",", ".", "/", "", "right shift", "", "up", ""],
            ["left ctrl", "left windows", "left menu", "", "", "", "space", "", "", "", "right menu", "right windows", "fn", "ctrl", "left", "down", "right"],
        ]
    }
    # ---------------------------------------------------------------------------
    TOOLCHAIN = {
        "path": "V:\\toolchain\\gcc-arm-none-eabi-10.3-2021.10\\bin\\",
        "options": [
            "-c",
            "-mcpu=cortex-m4",
            "-mthumb",
            "-DTHUMB_PRESENT",
            "-mno-thumb-interwork",
            "-DTHUMB_NO_INTERWORKING",
            "-mno-unaligned-access",
            "-mfloat-abi=hard",
            "-mfpu=fpv4-sp-d16",
            "-fsingle-precision-constant",
            "-fomit-frame-pointer",
            "-ffunction-sections",
            "-fdata-sections",
            "-fno-common",
            "-fshort-wchar",
            "-fno-builtin-printf",
            "-ggdb",
            "-Os",
            "-Wall",
            "-Wstrict-prototypes",
            "-Werror",
            "-std=gnu11",
            "-fcommon",
            "-fPIC",
        ],
        "include_base": "",
        "includes": [
            "quantum/rgb_matrix/animations",
            "quantum/rgb_matrix/",
            "quantum/",
            "platforms/",
            "keyboards/keychron/q3_max/",
        ],
    }
    # ---------------------------------------------------------------------------

    @classmethod
    def name(cls):
        return cls.NAME

    @classmethod
    def vid_pid(cls):
        return (cls.VID, cls.PID)

    @classmethod
    def mcu(cls):
        return cls.MCU

    @classmethod
    def matrix_size(cls):
        return (cls.MAXTRIX_W, cls.MAXTRIX_H)

    @classmethod
    def rgb_matrix_size(cls):
        return (cls.RGB_MAXTRIX_W, cls.RGB_MAXTRIX_H)

    @classmethod
    def rgb_max_refresh(cls):
        return cls.RGB_MAX_REFRESH

    @classmethod
    def num_rgb_leds(cls):
        return cls.NUM_RGB_LEDS

    @classmethod
    def default_layer(cls, mode):
        layer = cls.DEFAULT_LAYER[mode.lower()]
        return layer

    @classmethod
    def num_layers(cls):
        return cls.NUM_LAYERS

    @classmethod
    def hw(cls):
        """Return the MCU hardware profile (flash/RAM layout) or None.

        The MCU name is the first element of the MCU tuple; the hardware
        database (qmk/QMKata/hw/) is keyed on that name.
        """
        from qmk.QMKata import hw
        return hw.get(cls.MCU[0])

    @classmethod
    def module_flash_layout(cls):
        """Return list of (slot_id, slot_base_addr, slot_size) for every
        module flash slot defined by this keyboard's module loader config.

        Derived from the MCU sector table + per-keyboard MODULE_FLASH_*
        constants, so the data comes from a single source of truth
        (the MCU profile) rather than being hardcoded twice.
        """
        profile = cls.hw()
        if profile is None:
            return []
        slots = []
        slot_id = 0
        for sector_idx in range(
            cls.MODULE_FLASH_FIRST_SECTOR,
            cls.MODULE_FLASH_FIRST_SECTOR + cls.MODULE_FLASH_SECTOR_COUNT,
        ):
            sector = profile.sector_by_index(sector_idx)
            if sector is None:
                continue
            for slot_in_sector in range(cls.MODULE_FLASH_SLOTS_PER_SECTOR):
                base = sector.base + slot_in_sector * cls.MODULE_FLASH_SLOT_SIZE
                slots.append((slot_id, base, cls.MODULE_FLASH_SLOT_SIZE))
                slot_id += 1
        return slots

    # pixel position to (rgb) led index
    @staticmethod
    def xy_to_rgb_index(x, y):
        __ = -1
        xy_to_led = [
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, __, 13, 14, 15],
            [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32],
            [33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49],
            [50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 62, __, __, __],
            [63, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 74, __, 75, __],
            [76, 77, 78, 79, 79, 79, 79, 79, 79, 79, 80, 81, 82, 83, 84, 85, 86],
        ]
        try:
            # print(f"xy_to_led[{y}][{x}] = {xy_to_led[y][x]}")
            return xy_to_led[y][x]
        except:
            return -1

    # keyboard config/status/... representation for "treeview model"
    class KeybStruct:
        TYPES = {
            1: "bit",
            2: "uint8",
            3: "uint16",
            4: "uint32",
            5: "uint64",
            6: "float",
            0x80: "array",
            "bit": 1,
            "uint8": 2,
            "uint16": 3,
            "uint32": 4,
            "uint64": 5,
            "float": 6,
            "array": 0x80,
        }
        FLAGS = {
            1: "readonly",
            "readonly": 1,
        }

        @classmethod
        def struct_name(cls, sid):
            try:
                return cls.STRUCTS[sid][0]
            except:
                return "unknown"

        @classmethod
        def struct_field_name(cls, sid, fid):
            try:
                return cls.STRUCTS[sid][1][fid]
            except:
                return "unknown"

        @classmethod
        def struct_field_type(cls, ftype):
            try:
                if ftype & 0x80:
                    item_type = ftype & 0x7F
                    return "array:" + cls.TYPES[item_type]
                else:
                    return cls.TYPES[ftype]
            except:
                return "unknown"

        @classmethod
        def print_struct(cls, sid, sfields):
            sname = cls.struct_name(sid)
            print(f"struct[{sid}]: {sname}")
            for fid, field in sfields.items():
                field_name = cls.struct_field_name(sid, fid)
                field_type = cls.struct_field_type(field[0])
                try:
                    field_offset = field[1]
                except:
                    field_offset = -1
                try:
                    field_size = field[2]
                except:
                    field_size = -1
                print(
                    f"  field:{field_name}, "
                    f"type:{field_type}, "
                    f"offset:{field_offset}, "
                    f"size:{field_size}"
                )

        @classmethod
        def struct_model(cls, model, sid, sfields):
            from PySide6.QtGui import Qt, QStandardItemModel, QStandardItem

            def create_item(text, editable=False):
                item = QStandardItem(str(text))
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                return item

            def add_struct_to_model(model, sid, sfields):
                sname = cls.struct_name(sid)
                _item = create_item(sname)
                for fid, finfo in sfields.items():
                    # print(f"field_id:{fid}, field_info:{finfo}")
                    try:
                        field_name = create_item(cls.struct_field_name(sid, fid))
                        field_type = create_item(cls.struct_field_type(finfo[0]))
                        field_size = create_item(finfo[2])
                        field_flags = finfo[3]
                        if field_flags & cls.FLAGS["readonly"]:
                            editable = False
                        else:
                            editable = True
                        field_value = create_item("", editable=editable)
                        field = [field_name, field_type, field_size, field_value]
                        _item.appendRow(field)
                    except:
                        pass
                model.appendRow(_item)

            if model is None:
                model = QStandardItemModel()
                model.setHorizontalHeaderLabels(["field", "type", "size", "value"])

            add_struct_to_model(model, sid, sfields)
            return model

    class KeybConfiguration_v0_1(KeybStruct):
        CONFIG_DEBUG = {
            1: "enable",
            2: "matrix",
            3: "keyboard",
            4: "mouse",
        }
        CONFIG_DEBUG_USER = {
            1: "qmkata",
            2: "stats",
            3: "user animation",
            4: "module",
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
        STRUCTS = CONFIG

    class KeybStatus_v0_1(KeybStruct):
        STATUS_BATTERY = {
            1: "level",
            2: "voltage",
            3: "charging",
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
        STRUCTS = STATUS

    @classmethod
    def keyb_config(cls):
        return cls.KeybConfiguration_v0_1

    @classmethod
    def keyb_status(cls):
        return cls.KeybStatus_v0_1
