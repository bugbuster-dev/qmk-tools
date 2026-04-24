# Copyright (C) 2024 bugbuster
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA.

from PySide6 import QtCore
from PySide6.QtCore import Signal
from PySide6.QtGui import QImage, QColor, QPainter

import pyfirmata2, serial, time, numpy as np
import glob, inspect, os, importlib.util, struct
from pathlib import Path

from SerialRawHID import SerialRawHID
from DebugTracer import DebugTracer


# -------------------------------------------------------------------------------
# region list com ports
def list_com_ports():
    device_list = serial.tools.list_ports.comports()
    for device in device_list:
        print(f"{device}: vid={device.vid:04x}, pid={device.pid:04x}")


def find_com_port(vid, pid):
    device_list = serial.tools.list_ports.comports()
    for device in device_list:
        if device.vid == vid and (pid == None or device.pid == pid):
            return device.device
    return None


# endregion


# region combine images
def combine_qimages(img1, img2):
    # Ensure the images are the same size
    if img1.size() != img2.size():
        print("Images are not the same size!")
        return img1

    for x in range(img1.width()):
        for y in range(img1.height()):
            pixel1 = img1.pixel(x, y)
            pixel2 = img2.pixel(x, y)
            # Extract RGB values
            r1, g1, b1, _ = QColor(pixel1).getRgb()
            r2, g2, b2, _ = QColor(pixel2).getRgb()
            # Add the RGB values
            r = min(r1 + r2, QMKataKeyboard.MAX_RGB_VAL)
            g = min(g1 + g2, QMKataKeyboard.MAX_RGB_VAL)
            b = min(b1 + b2, QMKataKeyboard.MAX_RGB_VAL)
            # Set the new pixel value
            img1.setPixel(x, y, QColor(r, g, b).rgb())

    return img1


def combine_qimages_painter(img1, img2):
    # Ensure the images are the same size
    if img1.size() != img2.size():
        print("Images are not the same size!")
        return img1

    # Combine the images
    painter = QPainter(img1)
    painter.drawImage(0, 0, img2)  # Adjust coordinates as needed
    painter.end()
    return img1


# endregion


def bits_mask(len):
    return (1 << len) - 1


# -------------------------------------------------------------------------------
class DefaultKeyboardModel:
    RGB_MAXTRIX_W = 17
    RGB_MAXTRIX_H = 6
    NUM_RGB_LEDS = 102
    RGB_MAX_REFRESH = 5

    DEFAULT_LAYER = 2
    NUM_LAYERS = 8

    def __init__(self, name):
        self.name = name
        pass

    def xy_to_rgb_index(x, y):
        return y * DefaultKeyboardModel.RGB_MAXTRIX_W + x


class QMKataKeybCmd_v0_1:
    EXTENDED = 0  # extended command
    SET = 1  # set a value for 'ID_...'
    GET = 2  # get a value for 'ID_...'
    ADD = 3  # add a value to 'ID_...'
    DEL = 4  # delete a value from 'ID_...'
    PUB = 5  # battery status, mcu load, diagnostics, debug traces, ...
    SUB = 6  # todo subscribe to for example battery status, mcu load, ...
    RESPONSE = 0xF  # response to a command
    # ----------------------------------------------------
    ID_RGB_MATRIX_BUF = 1
    ID_DEFAULT_LAYER = 2
    ID_DEBUG_MASK = 3
    ID_BATTERY_STATUS = 4
    ID_MACWIN_MODE = 5
    ID_RGB_MATRIX_MODE = 6
    ID_RGB_MATRIX_HSV = 7
    ID_DYNLD_FUNCTION = 250  # dynamic loaded function
    ID_DYNLD_FUNEXEC = 251  # execute dynamic loaded function


class QMKataKeybCmd_v0_2(QMKataKeybCmd_v0_1):
    ID_CLI = 3  # debug mask deprecated
    ID_STATUS = 4
    ID_CONFIG_LAYOUT = 8
    ID_CONFIG = 9
    ID_KEYPRESS_EVENT = 10


class QMKataKeybCmd_v0_3(QMKataKeybCmd_v0_2):
    ID_STRUCT_LAYOUT = 8
    ID_STATUS = 4  # status, followed by specific id
    ID_CONFIG = 9  # config, followed by specific id
    ID_CONTROL = 11  # todo
    ID_EVENT = 10  # todo
    ID_COMBO = 11  # EEPROM-backed combo definitions
    ID_TAP_DANCE = 12
    ID_LEADER = 13
    ID_MODULE = 14


# use always latest, no plan for backward compatibility support for now
QMKataKeybCmd = QMKataKeybCmd_v0_3


class QMKataKeyboard(pyfirmata2.Board, QtCore.QObject):
    """
    A keyboard which "talks" qmkata.
    """

    # -------------------------------------------------------------------------------
    # signal received qmk keyboard data
    signal_console_output = Signal(str)
    signal_macwin_mode = Signal(str)
    signal_default_layer = Signal(int)
    signal_config_model = Signal(object)
    signal_status_model = Signal(object)
    # signal_control_model = Signal(object) # todo
    # signal_event_model = Signal(object) # todo
    signal_config = Signal(object)
    signal_status = Signal(object)
    signal_combo = Signal(object)
    signal_tap_dance = Signal(int, object)  # (slot, tap_dance_def bytes)
    signal_leader = Signal(int, object)  # (slot, leader_def bytes)
    signal_module_status = Signal(object)

    # -------------------------------------------------------------------------------
    MAX_RGB_VAL = 255

    # format: QImage.Format_RGB888 or QImage.Format_BGR888
    @staticmethod
    def convert_to_keyb_rgb(pixel, format, index, duration, brightness=(1.0, 1.0, 1.0)):
        if index < 0:
            return None
        ri = 0
        gi = 1
        bi = 2
        if format == QImage.Format_BGR888:
            ri = 2
            bi = 0
        # print(brightness)
        data = bytearray()
        data.append(index)
        data.append(duration)
        data.append(min(int(pixel[ri] * brightness[ri]), QMKataKeyboard.MAX_RGB_VAL))
        data.append(min(int(pixel[gi] * brightness[gi]), QMKataKeyboard.MAX_RGB_VAL))
        data.append(min(int(pixel[bi] * brightness[bi]), QMKataKeyboard.MAX_RGB_VAL))
        return data

    @staticmethod
    def load_keyboard_models(path="keyboards"):
        keyb_models = {}  # class name -> class
        keyb_models_vpid = {}  # vid/pid -> class

        path = Path(os.path.dirname(__file__)).joinpath(path)
        glob_filter = os.path.join(path, "[!_]*.py")
        model_files = glob.glob(glob_filter)
        # print(model_files)
        for file_path in model_files:
            module_name = os.path.basename(file_path)[:-3]  # Remove '.py' extension
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # Iterate through the attributes of the module
            for name, obj in inspect.getmembers(module):
                # Check if the attribute is a class defined in this module
                if inspect.isclass(obj) and obj.__module__ == module.__name__:
                    keyb_models[obj.NAME] = obj
                    keyb_models_vpid[obj.vid_pid()] = obj
        return keyb_models, keyb_models_vpid

    @staticmethod
    def attached_keyboards():
        import hid

        hid_devices = hid.enumerate()

        def device_attached(vendor_id, product_id):
            for device in hid_devices:
                if (
                    device["vendor_id"] == vendor_id
                    and device["product_id"] == product_id
                ):
                    return True
            return False

        keyboard_models = QMKataKeyboard.load_keyboard_models()
        keyboards = []
        print(f"keyboards: {keyboard_models[0]}")
        for model in keyboard_models[0].values():
            if device_attached(model.VID, model.PID):
                print(
                    f"keyboard found: {model.NAME} ({hex(model.VID)}:{hex(model.PID)})"
                )
                keyboards.append(model.NAME)
        return keyboards, keyboard_models[0]

    RAW_EPSIZE_FIRMATA = 64  # 32
    MAX_LEN_SYSEX_DATA = 60

    # -------------------------------------------------------------------------------
    # kb object in "keyboard script" tab
    class KeybScriptEnv:
        class DictOnReadWrite(dict):
            def __init__(self, on_read, on_write):
                self.on_read = on_read
                self.on_write = on_write

            def __getitem__(self, key):
                try:
                    return self.on_read(key)
                except:
                    return -1

            def __setitem__(self, key, val):
                try:
                    self.on_write(key, val)
                except:
                    return -1

        def __init__(self, keyboard, firmware_path=None):
            self.dbg = DebugTracer(zones={"D": 0}, obj=self)

            self.keyboard = keyboard
            self.firmware_path = firmware_path
            self._module_build = None
            self.pack_endian = "<"
            try:
                if self.keyboard.keyboardModel.MCU[2].startswith("be"):
                    self.pack_endian = ">"
            except:
                pass
            self.m = self.DictOnReadWrite(
                self.on_mem_read, self.on_mem_write
            )  # memory access
            self.e = self.DictOnReadWrite(
                self.on_eeprom_read, self.on_eeprom_write
            )  # eeprom access
            self.rgb = self.DictOnReadWrite(
                self.on_rgb_read, self.on_rgb_write
            )  # rgb matrix buffer access

            try:
                import GccMapfile

                self.mapfile = GccMapfile.GccMapfile(firmware_path=firmware_path)
                # Linker map symbols exposed to scripts as:
                #   kb.fun["symbol_name"] -> {"address", "size", ...}
                #   kb.var["symbol_name"] -> {"address", "size", ...}
                # Typical flow: addr = kb.fun["foo"]["address"]; kb.call(addr)
                self.fun = self.mapfile.functions
                self.var = self.mapfile.variables
            except Exception as e:
                self.dbg.tr("D", "mapfile: {}", e)
                # Map file is optional; scripts must handle missing kb.fun/kb.var.
                self.mapfile = None

            try:
                import GccToolchain

                self.toolchain = GccToolchain.GccToolchain(
                    self.keyboard.keyboardModel.TOOLCHAIN,
                    firmware_path=firmware_path,
                )
            except Exception as e:
                self.dbg.tr("D", "toolchain: {}", e)
                self.toolchain = None

        def on_mem_read(self, key):
            try:
                addr = key[0]
                size = key[1]
            except:
                addr = key
                size = 1
            self.dbg.tr(
                "D",
                "on_mem_read: key={key}, addr={addr}, size={size}",
                key=key,
                addr=addr,
                size=size,
            )
            resp = self.keyboard.keyb_set_cli_command(f"mr {hex(addr)} {size}")
            if size == 1:
                return resp[0]
            if size == 2:
                return struct.unpack_from(self.pack_endian + "H", resp)[0]
            if size == 4:
                return struct.unpack_from(self.pack_endian + "I", resp)[0]
            return resp

        def on_mem_write(self, key, val):
            try:
                addr = key[0]
                size = key[1]
            except:
                addr = key
                size = 1
            self.dbg.tr(
                "D",
                "on_mem_write: key={key}, addr={addr}, size={size}",
                key=key,
                addr=addr,
                size=size,
            )
            resp = self.keyboard.keyb_set_cli_command(
                f"mw {hex(addr)} {size} {hex(val)}"
            )

        def on_eeprom_read(self, key):
            if key == "l":  # layout
                resp = self.keyboard.keyb_set_cli_command("el")
                return resp
            try:
                addr = key[0]
                size = key[1]
            except:
                addr = key
                size = 1
            self.dbg.tr(
                "D",
                "on_eeprom_read: key={key}, addr={addr}, size={size}",
                key=key,
                addr=addr,
                size=size,
            )
            resp = self.keyboard.keyb_set_cli_command(f"er {hex(addr)} {size}")
            if size == 1:
                return resp[0]
            if size == 2:
                return struct.unpack_from(self.pack_endian + "H", resp)[0]
            if size == 4:
                return struct.unpack_from(self.pack_endian + "I", resp)[0]
            return resp

        def on_eeprom_write(self, key, val):
            try:
                addr = key[0]
                size = key[1]
            except:
                addr = key
                size = 1
            self.dbg.tr(
                "D",
                "on_eeprom_write: key={key}, addr={addr}, size={size}",
                key=key,
                addr=addr,
                size=size,
            )
            resp = self.keyboard.keyb_set_cli_command(
                f"ew {hex(addr)} {size} {hex(val)}"
            )

        def on_rgb_read(self, key):
            return None

        def on_rgb_write(self, key, val):
            self.dbg.tr("D", "on_rgb_write: key={key}, val={val}", key=key, val=val)
            rgb_index = key
            rgb_data = val
            # rgb matrix image or pixel(s)
            if key == "img":
                rgb_index = None
            self.keyboard.keyb_set_rgb_pixel((rgb_index, rgb_data))

        # call function at address
        def call(self, addr):
            # Sends a CLI "call" command to firmware: c <hex address>
            self.dbg.tr("D", "call: {addr}", addr=addr)
            resp = self.keyboard.keyb_set_cli_command(f"c {hex(addr)}")
            return resp

        def compile(self, c_file):
            if self.toolchain:
                elf_file = c_file.replace(".c", ".elf")
                bin_file = elf_file.replace(".elf", ".bin")
                if self.toolchain.compile(c_file, elf_file):
                    elf_data = None
                    bin_data = None
                    with open(elf_file, "rb") as f:
                        elf_data = f.read()
                    if self.toolchain.elf2bin(elf_file, bin_file):
                        with open(bin_file, "rb") as f:
                            bin_data = f.read()
                    return {"elf": elf_data, "bin": bin_data}
            return None

        # exec function
        def exec(self, code):
            if type(code) == str:
                # compile file
                c_file = code
                if not self.compile(c_file):
                    self.dbg.tr("D", "compile failed")
                    return None
                with open("exec.bin", "rb") as f:
                    code = f.read()
                    self.dbg.tr("D", code.hex(" "))

            if type(code) == bytes:
                # load function
                DYNLD_FUN_ID_EXEC = 1
                self.load_fun(DYNLD_FUN_ID_EXEC, code)
                resp = self.keyboard.keyb_set_dynld_funexec(DYNLD_FUN_ID_EXEC)
                return resp

        # load function
        def load_fun(self, fun_id, code):
            self.keyboard.keyb_set_dynld_function(fun_id, code)

        def _module_builder(self):
            if not self.toolchain:
                return None
            if self._module_build is None:
                from ModuleBuild import ModuleBuild

                self._module_build = ModuleBuild(
                    self.toolchain,
                    mapfile=self.mapfile,
                    firmware_path=self.firmware_path,
                )
            return self._module_build

        def build_module(self, source_file):
            builder = self._module_builder()
            if not builder:
                return None
            source_path = Path(source_file)
            if not source_path.is_absolute():
                source_path = Path(__file__).resolve().parent / source_path
            return builder.build(str(source_path))

        def load_module(self, slot_id, binary_or_result):
            binary = binary_or_result
            if isinstance(binary_or_result, dict):
                binary = binary_or_result["binary"]
            return self.keyboard.keyb_set_module(slot_id, binary)

        def unload_module(self, slot_id):
            return self.keyboard.keyb_del_module(slot_id)

        def set(self, key, val):
            self.dbg.tr("E", "todo")

        def get(self, key):
            self.dbg.tr("E", "todo")

    def __init__(self, *args, **kwargs):
        QtCore.QObject.__init__(self)
        # ----------------------------------------------------
        # region debug tracers
        self.dbg_rgb_buf = 0
        self.dbg = DebugTracer(
            zones={
                "D": 0,
                "CONSOLE": 0,
                "CLI": 0,
                "SYSEX_COMMAND": 0,
                "SYSEX_RESPONSE": 0,
                "SYSEX_PUB": 0,
                "RGB_BUF": self.dbg_rgb_buf,
            },
            obj=self,
        )
        # endregion

        # ----------------------------------------------------
        self.samplerThread = None

        self.img = {}  # sender -> rgb QImage
        self.img_ts_prev = 0  # previous image timestamp

        self.name = None
        self.port = None
        self.vid_pid = None
        self.firmware_path = None
        for arg in kwargs:
            if arg == "name":
                self.name = kwargs[arg]
            if arg == "port":
                self.port = kwargs[arg]
            if arg == "vid_pid":
                self.vid_pid = kwargs[arg]
            if arg == "firmware_path":
                self.firmware_path = kwargs[arg]

        if self.name == None:
            self.name = self.port

        self.port_type = "serial"

        # load "keyboard models", keyboard model contains name, vid/pid, rgb matrix size, ...
        self.keyboardModel, self.keyboardModelVidPid = self.load_keyboard_models()
        for class_name, class_type in self.keyboardModel.items():
            self.dbg.tr(
                "D",
                f"keyboard model: {class_name} ({hex(class_type.vid_pid()[0])}:{hex(class_type.vid_pid()[1])}), {class_type}",
            )

        self.keyb_poll_time = 1 / 1000

        if self.port == None and self.vid_pid:
            self.keyboardModel = self.keyboardModelVidPid[
                (self.vid_pid[0], self.vid_pid[1])
            ]
            try:
                self.port_type = self.keyboardModel.PORT_TYPE
            except Exception as e:
                pass

            self.port = find_com_port(self.vid_pid[0], self.vid_pid[1])
            self.dbg.tr(
                "D", "using keyboard: {} on port {}", self.keyboardModel, self.port
            )
            self.name = self.keyboardModel.name()
            self._rgb_max_refresh = self.rgb_max_refresh()
        self.kb_script_env = self.KeybScriptEnv(self, firmware_path=self.firmware_path)

        self.samplerThread = pyfirmata2.util.Iterator(self)
        if self.port_type == "rawhid":
            self.sp = SerialRawHID(
                self.vid_pid[0], self.vid_pid[1], self.RAW_EPSIZE_FIRMATA
            )
            self.MAX_LEN_SYSEX_DATA = (
                self.RAW_EPSIZE_FIRMATA - 6
            )  # 2 bytes for report id + firmata msg id, 2 bytes for sysex start/end, 1 byte for sysex cmd, 1 byte for seqnum
        else:
            self.sp = serial.Serial(self.port, 115200, timeout=1)

        # pretend its an arduino
        self._layout = pyfirmata2.BOARDS["arduino"]
        if not self.name:
            self.name = self.port

    def __str__(self):
        return "{0.name} ({0.sp.port})".format(self)

    # -------------------------------------------------------------------------------
    def rgb_matrix_size(self):
        if self.keyboardModel:
            return self.keyboardModel.rgb_matrix_size()
        return DefaultKeyboardModel.RGB_MAXTRIX_W, DefaultKeyboardModel.RGB_MAXTRIX_H

    def rgb_max_refresh(self):
        if self.keyboardModel:
            return self.keyboardModel.rgb_max_refresh()
        return DefaultKeyboardModel.RGB_MAX_REFRESH

    def num_layers(self):
        if self.keyboardModel:
            return self.keyboardModel.num_layers()
        return DefaultKeyboardModel.NUM_LAYERS

    def num_rgb_leds(self):
        if self.keyboardModel:
            return self.keyboardModel.num_rgb_leds()
        return DefaultKeyboardModel.NUM_RGB_LEDS

    def default_layer(self, mode):
        try:
            if self.keyboardModel:
                return self.keyboardModel.default_layer(mode)
        except Exception as e:
            self.dbg.tr("D", "default_layer: {}", e)
        return DefaultKeyboardModel.DEFAULT_LAYER

    def xy_to_rgb_index(self, x, y):
        xy_to_rgb_index = DefaultKeyboardModel.xy_to_rgb_index
        if self.keyboardModel:
            xy_to_rgb_index = self.keyboardModel.xy_to_rgb_index
        return xy_to_rgb_index(x, y)

    # -------------------------------------------------------------------------------
    def start(self):
        from KeyMachine import KeyMachine

        # byte to 2x 7 bit bytes
        def to_two_bytes(byte_val):
            return bytearray([byte_val % 128, byte_val >> 7])

        self.lookup_table_sysex_byte = {}
        for i in range(256):
            self.lookup_table_sysex_byte[i] = to_two_bytes(i)

        if self._layout:
            self.setup_layout(self._layout)
        else:
            self.auto_setup()

        self.pack_endian = "<"  # most likely little endian
        try:
            if self.keyboardModel.MCU[2].startswith("be"):
                self.pack_endian = ">"  # big endian
        except:
            pass

        self.key_machine = KeyMachine(self)

        self.sysex_response = {}
        self.sysex_response[QMKataKeybCmd.ID_CLI] = {}
        self.sysex_response[QMKataKeybCmd.ID_DYNLD_FUNEXEC] = {}
        self.sysex_response_seq = {}
        self.sysex_seqnum = 0
        self.keyb_cli_seqnum = (
            0  # todo: remove when sysex message sequence number is used
        )

        self.struct_layout = {}
        self.struct_model = {}
        self.struct_model[QMKataKeybCmd.ID_CONFIG] = None
        self.struct_model[QMKataKeybCmd.ID_STATUS] = None

        self.encode_7bits_sysex = False
        self.add_cmd_handler(pyfirmata2.STRING_DATA, self.console_line_handler)
        self.add_cmd_handler(QMKataKeybCmd.RESPONSE, self.sysex_response_handler)
        self.add_cmd_handler(QMKataKeybCmd.PUB, self.sysex_pub_handler)

        self.samplingOn()
        self.send_sysex(pyfirmata2.REPORT_FIRMWARE, [])
        self.send_sysex(
            QMKataKeybCmd.GET, [QMKataKeybCmd.ID_STRUCT_LAYOUT, QMKataKeybCmd.ID_CONFIG]
        )
        self.send_sysex(
            QMKataKeybCmd.GET,
            [QMKataKeybCmd.ID_STRUCT_LAYOUT, QMKataKeybCmd.ID_CONTROL],
        )
        self.send_sysex(
            QMKataKeybCmd.GET, [QMKataKeybCmd.ID_STRUCT_LAYOUT, QMKataKeybCmd.ID_STATUS]
        )
        self.send_sysex(
            QMKataKeybCmd.GET, [QMKataKeybCmd.ID_STRUCT_LAYOUT, QMKataKeybCmd.ID_EVENT]
        )
        self.send_sysex(QMKataKeybCmd.GET, [QMKataKeybCmd.ID_MACWIN_MODE])

        time.sleep(0.5)
        print("-" * 80)
        print(f"{self}")
        print(
            f"qmkata version:{self.firmware} {self.firmware_version}, firmata={self.get_firmata_version()}"
        )
        print(f"mcu:{self.keyboardModel.MCU} {self.pack_endian}")
        print("-" * 80)
        # signal config structs/values model
        try:
            self.signal_config_model.emit(self.struct_model[QMKataKeybCmd.ID_CONFIG])
        except Exception as e:
            self.dbg.tr("E", "{}", e)
        # signal status structs/values model
        try:
            self.signal_status_model.emit(self.struct_model[QMKataKeybCmd.ID_STATUS])
        except Exception as e:
            self.dbg.tr("E", "{}", e)

        # get config structs/values
        try:
            for config_id in self.struct_layout[QMKataKeybCmd.ID_CONFIG]:
                self.send_sysex(QMKataKeybCmd.GET, [QMKataKeybCmd.ID_CONFIG, config_id])
        except Exception as e:
            self.dbg.tr("E", "{}", e)
        time.sleep(0.5)
        # get status structs/values
        try:
            for status_id in self.struct_layout[QMKataKeybCmd.ID_STATUS]:
                self.send_sysex(QMKataKeybCmd.GET, [QMKataKeybCmd.ID_STATUS, status_id])
        except Exception as e:
            self.dbg.tr("E", "{}", e)

        # auto-load combo/tap_dance/leader EEPROM slots
        time.sleep(0.3)
        for slot in range(16):
            self.keyb_get_combo(slot)
        for slot in range(8):
            self.keyb_get_tap_dance(slot)
        for slot in range(8):
            self.keyb_get_leader(slot)

    def stop(self):
        try:
            self.sp.close()
        except Exception as e:
            self.dbg.tr("E", "stop: {}", e)
        self.samplingOff()

    # -------------------------------------------------------------------------------
    # qmkata sysex send: START_SYSEX+1 and include sequence number in payload and
    # no byte to 2x 7 bits encoding
    def send_sysex(self, sysex_cmd, data):
        if len(data) > self.MAX_LEN_SYSEX_DATA:
            self.dbg.tr("E", "send_sysex: data len too large {}", len(data))
            return

        encoded_data = data
        if self.encode_7bits_sysex:  # 2x 7 bits to byte
            encoded_data = bytearray()
            for i in range(len(data)):
                encoded_data.extend(self.lookup_table_sysex_byte[data[i]])
            # print(f"sysex_cmd:{sysex_cmd}, encoded len:{len(encoded_data)}")
            # print(f"encoded data:{encoded_data.hex(' ')}")
            super().send_sysex(sysex_cmd, encoded_data)
            return

        seqnum = self.sysex_seqnum
        msg = bytearray([pyfirmata2.START_SYSEX + 1, sysex_cmd, seqnum])
        msg.extend(encoded_data)
        msg.append(
            pyfirmata2.END_SYSEX
        )  # todo: remove, not needed when processing directly from rawhid buffer on device, only needed when putting first in "serial buffer" and process it later
        try:
            n_written = self.sp.write(msg)
        except Exception as e:
            self.dbg.tr("E", "send_sysex: {}", e)
            return 0
        self.sysex_seqnum = (self.sysex_seqnum + 1) % 256
        return n_written, seqnum

    def _sysex_data_to_bytearray(self, data):
        buf = bytearray()
        if len(data) % 2 != 0:
            self.dbg.tr("E", "sysex data: invalid data length {}", len(data))
            return None

        for off in range(0, len(data), 2):
            # 2x 7 bit bytes to 1 byte
            buf.append(data[off + 1] << 7 | data[off])
        return buf

    def sysex_pub_handler(self, *data):
        dbg_zone = "SYSEX_PUB"
        dbg_print = self.dbg.enabled(dbg_zone)
        if not (buf := self._sysex_data_to_bytearray(data)):
            return
        if dbg_print:
            self.dbg.tr(dbg_zone, "-" * 40)
            self.dbg.tr(dbg_zone, "sysex pub:\n{}", buf.hex(" "))

        if buf[0] == QMKataKeybCmd.ID_KEYPRESS_EVENT:
            col = buf[1]
            row = buf[2]
            time = struct.unpack_from(self.pack_endian + "H", buf, 3)[0]
            type = buf[5]
            pressed = buf[6]
            # dbg.tr('KEYPRESS_EVENT', f"key press event: row={row}, col={col}, time={time}, type={type}, pressed={pressed}")
            if self.key_machine:
                self.key_machine.key_event(row, col, time, pressed)

    # -------------------------------------------------------------------------------
    def sysex_response_handler(self, *data):
        dbg_zone = "SYSEX_RESPONSE"
        dbg_print = self.dbg.enabled(dbg_zone)

        def dbg(*args, **kwargs):
            if self.dbg.enabled(dbg_zone):
                self.dbg.tr(dbg_zone, *args, **kwargs)

        if not (buf := self._sysex_data_to_bytearray(data)):
            return
        if dbg_print:
            dbg("-" * 40)
            dbg("sysex response:\n{}", buf.hex(" "))

        try:
            seqnum = buf[0]
            buf = buf[1:]
            if buf[0] == QMKataKeybCmd.ID_CLI:
                dbg("cli response: {}", buf)
                cli_seq = buf[1]
                buf.pop(0)
                buf.pop(0)
                self.sysex_response[QMKataKeybCmd.ID_CLI][cli_seq] = buf
                return
            if buf[0] == QMKataKeybCmd.ID_DYNLD_FUNCTION:
                return_code = buf[1]
                self.sysex_response_seq[seqnum] = return_code
                dbg("dynld set function response: {}, {}", buf, return_code)
                return
            if buf[0] == QMKataKeybCmd.ID_DYNLD_FUNEXEC:
                dbg("dynld funexec response: {}", buf)
                return_code = struct.unpack_from(self.pack_endian + "I", buf, 1)[0]
                self.sysex_response[QMKataKeybCmd.ID_DYNLD_FUNEXEC] = return_code
                # buf.pop(0); buf.pop(0)
                return
            if buf[0] == QMKataKeybCmd.ID_MACWIN_MODE:
                macwin_mode = chr(buf[1])
                dbg("macwin mode: {}", macwin_mode)
                self.signal_macwin_mode.emit(macwin_mode)
                self.signal_default_layer.emit(self.default_layer(macwin_mode))
                return
            if buf[0] == QMKataKeybCmd.ID_COMBO:
                slot_back = buf[1]
                keys_raw = buf[2:18]
                keycode_raw = buf[18:20]
                keys = []
                for i in range(0, 16, 2):
                    keys.append(
                        struct.unpack_from(self.pack_endian + "H", keys_raw, i)[0]
                    )
                keycode = struct.unpack_from(self.pack_endian + "H", keycode_raw, 0)[0]
                dbg("combo slot:{}, keys:{}, keycode:{}", slot_back, keys, keycode)
                self.signal_combo.emit(
                    {"slot": slot_back, "keys": keys, "keycode": keycode}
                )
                return
            if buf[0] == QMKataKeybCmd.ID_TAP_DANCE:
                # buf: [ID_TAP_DANCE, slot, kc1_lo, kc1_hi, kc2_lo, kc2_hi,
                #                          kc3_lo, kc3_hi, hold_lo, hold_hi]
                if len(buf) >= 10:
                    slot = buf[1]
                    self.signal_tap_dance.emit(slot, bytes(buf[2:10]))
                return
            if buf[0] == QMKataKeybCmd.ID_LEADER:
                # buf: [ID_LEADER, slot, seq0_lo, seq0_hi, ..., seq4_lo, seq4_hi, kc_lo, kc_hi]
                if len(buf) >= 14:  # 1 (id) + 1 (slot) + 12 (leader_def_t)
                    slot = buf[1]
                    self.signal_leader.emit(slot, bytes(buf[2:14]))
                return
            if buf[0] == QMKataKeybCmd.ID_MODULE:
                if len(buf) <= 2:
                    # Chunk ACK or DEL response (3 bytes on wire incl. seqnum)
                    self.sysex_response_seq[seqnum] = buf[1]
                    dbg("module ACK response: {}, rc={}", buf, buf[1])
                    return
                if buf[1] == 0xFF:
                    # GET summary response
                    payload_len = len(buf) - 2
                    if payload_len % 4 != 0:
                        dbg(
                            "module summary: invalid payload len={}, buf_len={}",
                            payload_len,
                            len(buf),
                        )
                        return
                    slot_count = payload_len // 4
                    magics = []
                    slots = []
                    for i in range(slot_count):
                        magic = struct.unpack_from("<I", buf, 2 + i * 4)[0]
                        magics.append(magic)
                        slots.append(1 if magic == 0x4D4F444C else 0)
                    dbg("module summary: slot_count={}, slots={}, magics={}", slot_count, slots, magics)
                    self.signal_module_status.emit(
                        {
                            'type': 'summary',
                            'slot_count': slot_count,
                            'slots': slots,
                            'magics': magics,
                        }
                    )
                    return
                if len(buf) == 13:
                    # GET single-slot header response (magic+flags+hook_bitmap)
                    slot_id = buf[1]
                    magic = struct.unpack_from("<I", buf, 2)[0]
                    flags = struct.unpack_from("<H", buf, 6)[0]
                    hook_bitmap = struct.unpack_from("<I", buf, 8)[0]
                    dbg("module slot: id={}, magic={:#x}, flags={:#x}, hook_bitmap={:#x}",
                        slot_id, magic, flags, hook_bitmap)
                    self.signal_module_status.emit(
                        {'type': 'slot', 'slot_id': slot_id, 'magic': magic,
                         'flags': flags, 'hook_bitmap': hook_bitmap}
                    )
                    return
                # Chunked binary read response (6+chunk bytes, never 13):
                # [ID_MODULE, slot_id, off_lo, off_hi, chunk_len, data...]
                self.sysex_response_seq[seqnum] = buf
                dbg("module binary chunk: slot={} off={} len={}",
                    buf[1], buf[2] | (buf[3] << 8), buf[4])
                return
            if buf[0] == QMKataKeybCmd.ID_STRUCT_LAYOUT:
                layout_id = buf[1]
                off = 2
                # struct layout used to get/set of struct field values in byte buffer
                struct_id = buf[off]
                off += 1
                struct_size = buf[off]
                off += 1
                struct_flags = buf[off]
                off += 1
                dbg(
                    "layout id: {}, struct id: {}, size: {}, flags: {}",
                    layout_id,
                    struct_id,
                    struct_size,
                    struct_flags,
                )
                struct_fields = {}
                struct_field = buf[off]
                while struct_field != 0:
                    field_type = buf[off + 1]
                    field_offset = buf[off + 2]
                    field_size = buf[off + 3]
                    struct_fields[struct_field] = (
                        field_type,
                        field_offset,
                        field_size,
                        struct_flags,
                    )
                    off += 4
                    try:
                        struct_field = buf[off]
                    except:
                        break

                if layout_id not in self.struct_layout:
                    self.struct_layout[layout_id] = {}
                self.struct_layout[layout_id][struct_id] = struct_fields

                try:
                    struct_model = self.struct_model[layout_id]
                except:
                    struct_model = None

                if layout_id == QMKataKeybCmd.ID_CONFIG:
                    if dbg_print:
                        self.keyboardModel.keyb_config().print_struct(
                            struct_id, struct_fields
                        )
                    self.struct_model[layout_id] = (
                        self.keyboardModel.keyb_config().struct_model(
                            struct_model, struct_id, struct_fields
                        )
                    )
                if layout_id == QMKataKeybCmd.ID_STATUS:
                    if dbg_print:
                        self.keyboardModel.keyb_status().print_struct(
                            struct_id, struct_fields
                        )
                    self.struct_model[layout_id] = (
                        self.keyboardModel.keyb_status().struct_model(
                            struct_model, struct_id, struct_fields
                        )
                    )

                return
            if buf[0] == QMKataKeybCmd.ID_STATUS or buf[0] == QMKataKeybCmd.ID_CONFIG:
                TYPE_BIT = self.keyboardModel.KeybStruct.TYPES["bit"]
                TYPE_UINT8 = self.keyboardModel.KeybStruct.TYPES["uint8"]
                TYPE_UINT16 = self.keyboardModel.KeybStruct.TYPES["uint16"]
                TYPE_UINT32 = self.keyboardModel.KeybStruct.TYPES["uint32"]
                TYPE_UINT64 = self.keyboardModel.KeybStruct.TYPES["uint64"]
                TYPE_FLOAT = self.keyboardModel.KeybStruct.TYPES["float"]
                TYPE_ARRAY = self.keyboardModel.KeybStruct.TYPES["array"]

                struct_fields = None
                struct_id = buf[1]
                if buf[0] == QMKataKeybCmd.ID_CONFIG:
                    struct_fields = self.struct_layout[QMKataKeybCmd.ID_CONFIG][
                        struct_id
                    ]
                if buf[0] == QMKataKeybCmd.ID_STATUS:
                    struct_fields = self.struct_layout[QMKataKeybCmd.ID_STATUS][
                        struct_id
                    ]

                if not struct_fields:
                    return

                off = 2
                field_values = {}
                for field_id, field in struct_fields.items():
                    field_type = field[0]
                    field_offset = field[1]
                    field_size = field[2]
                    off = 2 + field_offset
                    if field_type == TYPE_BIT:
                        # todo: if msb bit order reverse bits, handle big endian, bitfield crossing byte boundary
                        off = 2 + field_offset // 8
                        field_offset = field_offset % 8
                        if field_size == 1:
                            value = 1 if buf[off] & (1 << field_offset) != 0 else 0
                            dbg(
                                "struct[{struct_id}][{field_id}]:off={off}, offset={field_offset}, value={value}",
                                struct_id=struct_id,
                                field_id=field_id,
                                off=off,
                                field_offset=field_offset,
                                value=value,
                            )
                        else:
                            value = (buf[off] >> field_offset) & bits_mask(field_size)
                    elif field_type == TYPE_UINT8:  # todo: test all types
                        value = buf[off]
                    elif field_type == TYPE_UINT16:
                        value = struct.unpack_from(self.pack_endian + "H", buf, off)[0]
                    elif field_type == TYPE_UINT32:
                        value = struct.unpack_from(self.pack_endian + "I", buf, off)[0]
                    elif field_type == TYPE_UINT64:
                        value = struct.unpack_from(self.pack_endian + "Q", buf, off)[0]
                    elif field_type == TYPE_FLOAT:
                        value = struct.unpack_from(self.pack_endian + "f", buf, off)[0]
                    elif (field_type & TYPE_ARRAY) == TYPE_ARRAY:
                        item_type = field_type & ~TYPE_ARRAY
                        # array item size
                        if item_type == TYPE_UINT8:
                            item_type_size = 1
                        elif item_type == TYPE_UINT16:
                            item_type_size = 2
                        elif item_type == TYPE_UINT32:
                            item_type_size = 4
                        elif item_type == TYPE_UINT64:
                            item_type_size = 8
                        elif item_type == TYPE_FLOAT:
                            item_type_size = 4
                        value = buf[off : off + (field_size * item_type_size)]
                    else:
                        value = 0
                    field_values[field_id] = value
                    dbg(
                        "struct[{struct_id}][{field_id}]: {value}",
                        struct_id=struct_id,
                        field_id=field_id,
                        value=value,
                    )
                    if off >= len(buf):
                        break

                # signal to gui the config values
                if buf[0] == QMKataKeybCmd.ID_CONFIG:
                    self.signal_config.emit((struct_id, field_values))
                if buf[0] == QMKataKeybCmd.ID_STATUS:
                    self.signal_status.emit((struct_id, field_values))
                return
        except Exception as e:
            self.dbg.tr("E", "{}", e)

    def console_line_handler(self, *data):
        # self.dbg.tr('CONSOLE', "console:{}", data)
        if len(data) % 2 != 0:
            data = data[:-1]
        line = self._sysex_data_to_bytearray(data).decode("utf-8", "ignore")
        if line:
            self.signal_console_output.emit(line)

    def run_script(self, script, signal_output=None):
        import threading

        # todo: check where locks are needed
        def run_script_on_thread(script, signal_output):
            from contextlib import redirect_stdout
            from io import StringIO

            class ScriptOutput(StringIO):
                def __init__(self, signal_output):
                    self.signal_output = signal_output
                    super().__init__()

                def write(self, string):
                    if self.signal_output:
                        self.signal_output.emit(string)

            globals_dict = globals()
            # Expose keyboard script environment to user scripts as `kb`.
            globals_dict.update({"kb": self.kb_script_env})
            script_output = ScriptOutput(signal_output)
            with redirect_stdout(script_output):
                exec(script, globals_dict, {"stopped": self.script_stopped})

        # stop previous script
        self.script_stop = True
        try:
            self.script_thread.join()
        except:
            pass

        self.script_stop = False
        self.script_thread = threading.Thread(
            target=run_script_on_thread,
            name="run_script_on_thread",
            args=(script, signal_output),
        )
        self.script_thread.start()

    # stopped() called from script to check if script should stop
    def script_stopped(self):
        return self.script_stop

    # -------------------------------------------------------------------------------
    def wait_for_response(self, seqnum, timeout_s=None):
        """Wait for a sysex response with the given seqnum.

        timeout_s: overall timeout. Defaults to keyb_poll_time * 100 (~100ms).
            Callers performing operations known to block the firmware for
            >100ms (e.g. flash sector erase) should pass a larger timeout
            to avoid spurious retries that queue up identical commands in
            the USB stack while the firmware is busy.
        """
        if timeout_s is None:
            timeout_s = self.keyb_poll_time * 100
        timed_out = False
        start = now = time.monotonic()
        while not timed_out:
            time.sleep(self.keyb_poll_time)
            if seqnum in self.sysex_response_seq:
                return True, self.sysex_response_seq.pop(seqnum, None)
            now = time.monotonic()
            timed_out = now - start > timeout_s
        self.dbg.tr(
            "E", "response timeout seqnum:{} start-now:{}-{}", hex(seqnum), start, now
        )
        return None

    # send and wait for response
    def send_sysex_wait(self, sysex_cmd, data, timeout_s=None):
        """Send sysex and wait for matching-seqnum response.

        timeout_s: per-attempt timeout (passed to wait_for_response).
            Default ~100ms. Slow firmware operations (flash erase) should
            pass a larger timeout to avoid spurious retries.
        """
        response_received = None
        num_sends = 0
        while not response_received:
            _, seqnum = self.send_sysex(sysex_cmd, data)
            self.dbg.tr("SYSEX_COMMAND", "cmd:{}, seqnum:{}", sysex_cmd, seqnum)
            num_sends += 1
            response_received = self.wait_for_response(seqnum, timeout_s=timeout_s)
            if num_sends > 10:
                self.dbg.tr("E", "response not received {}", seqnum)
                return False
        return response_received

    def keyb_set_cli_command(self, cmd):
        dbg_zone = "CLI"
        dbg_print = self.dbg.enabled(dbg_zone)
        self.dbg.tr(dbg_zone, "keyb_set_cli_command: {}", cmd)

        if cmd.strip() == "":
            return None

        def cli_cmd_encode(cmd_str, endian):
            CLI_CMD_MEMORY = 0x01
            CLI_CMD_EEPROM = 0x02
            CLI_CMD_CALL = 0x03
            CLI_CMD_LAYOUT = 0x40
            CLI_CMD_WRITE = 0x80
            try:
                cmd_args = cmd_str.strip().split(" ")
                cmd = cmd_args[0]
                if cmd[0] == "m" or cmd[0] == "e":
                    cli_cmd = CLI_CMD_MEMORY if cmd[0] == "m" else CLI_CMD_EEPROM
                    if cmd[1] == "l" and cli_cmd == CLI_CMD_EEPROM:
                        ba = bytearray([cli_cmd | CLI_CMD_LAYOUT])
                        return ba
                    if cmd[1] == "r":
                        addr = int(cmd_args[1], 16)
                        size = int(cmd_args[2])
                        # print(f"cli_cmd_encode: {cli_cmd}, {addr}, {size}")
                        ba = bytearray([cli_cmd])
                        return (
                            ba
                            + bytearray(struct.pack(endian + "I", addr))
                            + bytearray([size % 256])
                        )
                    if cmd[1] == "w":
                        addr = int(cmd_args[1], 16)
                        size = int(cmd_args[2])
                        val = int(cmd_args[3], 16)
                        # print(f"cli_cmd_encode: {cli_cmd}, {addr}, {size}, {val}")
                        ba = bytearray([cli_cmd | CLI_CMD_WRITE])
                        return (
                            ba
                            + bytearray(struct.pack(endian + "I", addr))
                            + bytearray([size % 256])
                            + bytearray(struct.pack(endian + "I", val))
                        )
                if cmd[0] == "c":
                    addr = int(cmd_args[1], 16)
                    # print(f"cli_cmd_encode: {CLI_CMD_CALL}, {addr}")
                    return bytearray([CLI_CMD_CALL]) + bytearray(
                        struct.pack(endian + "I", addr)
                    )
            except:
                return None

        cmd_ba = cli_cmd_encode(cmd, self.pack_endian)
        if dbg_print:
            self.dbg.tr(dbg_zone, "keyb_set_cli_command: cmd_ba: {}", cmd_ba.hex(" "))

        cli_seq = self.keyb_cli_seqnum % 256
        self.keyb_cli_seqnum += 1
        data = bytearray()
        try:
            data.append(QMKataKeybCmd.ID_CLI)
            data.append(cli_seq)
            data.extend(cmd_ba)
            self.send_sysex(QMKataKeybCmd.SET, data)
        except Exception as e:
            self.dbg.tr("E", "keyb_set_cli_command: {}", e)
            return None

        # wait for response
        wait_for_response = True
        response = None
        if wait_for_response:
            timed_out = False
            start = time.monotonic()
            while response == None and not timed_out:
                time.sleep(self.keyb_poll_time * 2)
                try:
                    response = self.sysex_response[QMKataKeybCmd.ID_CLI][cli_seq]
                    del self.sysex_response[QMKataKeybCmd.ID_CLI][cli_seq]
                except:
                    timed_out = time.monotonic() - start > self.keyb_poll_time * 100

            if dbg_print:
                response_str = "none"
                if response:
                    response_str = response.hex(" ")
                self.dbg.tr(
                    dbg_zone, "keyb_set_cli_command: response: {}", response_str
                )
        return response

    def keyb_set_rgb_pixel(self, pixels):
        rgb_index = pixels[0]
        rgb_data = pixels[1]
        if type(rgb_index) == tuple:
            rgb_index = list(rgb_index)
        elif type(rgb_index) == int:
            rgb_index = [rgb_index]

        self.dbg.tr("RGB_BUF", "keyb_set_rgb_pixel: {} {}", rgb_index, rgb_data)
        if rgb_index == None:
            # todo: qimage from rgb_data
            # rgb_image = ...
            # self.keyb_set_rgb_image(rgb_image, 1.0)
            print("todo: full rgb image")
            return

        if rgb_index == "duration":
            self.rgb_pixel_duration = rgb_data
        try:
            pixel_duration = self.rgb_pixel_duration
        except:
            pixel_duration = 100

        data = bytearray()
        data.append(QMKataKeybCmd.ID_RGB_MATRIX_BUF)
        for i in range(len(rgb_index)):
            pixel = rgb_data
            try:
                if type(rgb_data[0]) == list:
                    pixel = rgb_data[i]
            except:
                pass

            rgb_pixel = self.convert_to_keyb_rgb(
                pixel, QImage.Format_RGB888, rgb_index[i], pixel_duration
            )
            if rgb_pixel:
                # self.dbg.tr('RGB_BUF', "pixel: {}", rgb_pixel.hex(' '))
                data.extend(rgb_pixel)

        # self.dbg.tr('RGB_BUF', "rgb data: {}", data.hex(' '))
        self.send_sysex(QMKataKeybCmd.SET, data)

    def keyb_set_rgb_image(self, img, rgb_multiplier):
        dbg_zone = "RGB_BUF"
        if self.dbg_rgb_buf:
            self.dbg.tr(dbg_zone, "-" * 120)
            self.dbg.tr(dbg_zone, "rgb mult {}", rgb_multiplier)

        # self.dbg.tr('D', "rgb img from sender {} {}", self.sender(), img)
        if not img:
            self.dbg.tr("D", "rgb sender {} stopped", self.sender())
            if self.sender() in self.img:
                self.img.pop(self.sender())
            return

        # multiple images senders -> combine images
        combined_img = img
        # prev_img = self.img[self.sender()]
        if len(self.img) > 1:
            combined_img = img.copy()
            for key in self.img:
                if key != self.sender():
                    # self.dbg.tr('D', "combine image from {}", key)
                    combined_img = combine_qimages(combined_img, self.img[key])

        # if not self.sender() in self.img:
        # self.dbg.tr('D', "new sender {} {}", self.sender(), img)
        self.img[self.sender()] = img
        img = combined_img
        # max refresh
        if time.monotonic() - self.img_ts_prev < 1 / self._rgb_max_refresh:
            if self.dbg_rgb_buf:
                self.dbg.tr(dbg_zone, "skip")
            return
        self.img_ts_prev = time.monotonic()

        # -------------------------------------------------------------------------------
        # iterate through the qimage pixels and convert to "keyboard rgb pixels" and send to keyboard
        height = img.height()
        width = img.width()
        arr = np.ndarray(
            (height, width, 3),
            buffer=img.constBits(),
            strides=[img.bytesPerLine(), 3, 1],
            dtype=np.uint8,
        )

        img_format = img.format()
        RGB_PIXEL_SIZE = 5
        num_sends = 0
        data = bytearray()
        data.append(QMKataKeybCmd.ID_RGB_MATRIX_BUF)
        for y in range(height):
            for x in range(width):
                pixel = arr[y, x]
                rgb_pixel = self.convert_to_keyb_rgb(
                    pixel, img_format, self.xy_to_rgb_index(x, y), 50, rgb_multiplier
                )
                if rgb_pixel:
                    data.extend(rgb_pixel)

                if self.dbg_rgb_buf:
                    self.dbg.tr(
                        dbg_zone,
                        f"{x:2},{y:2}=({pixel[0]:3},{pixel[1]:3},{pixel[2]:3})",
                        end=" ",
                    )
                    self.dbg.tr(dbg_zone, rgb_pixel.hex(" "))

                if len(data) + RGB_PIXEL_SIZE > self.MAX_LEN_SYSEX_DATA:
                    self.send_sysex(QMKataKeybCmd.SET, data)
                    num_sends += 1
                    # todo sync with keyboard to avoid buffer overflow
                    # depends on keyboard, put parameter in "keyboard model" class
                    if self.port_type == "rawhid":  # keychron q3 max
                        if num_sends % 10 == 0:
                            time.sleep(self.keyb_poll_time * 2)
                    else:
                        if num_sends % 2 == 0:
                            time.sleep(self.keyb_poll_time * 2)

                    data = bytearray()
                    data.append(QMKataKeybCmd.ID_RGB_MATRIX_BUF)

        if len(data) > RGB_PIXEL_SIZE:
            self.send_sysex(QMKataKeybCmd.SET, data)
            num_sends += 1

    def keyb_set_default_layer(self, layer):
        self.dbg.tr("SYSEX_COMMAND", "keyb_set_default_layer: {}", layer)
        data = bytearray()
        data.append(QMKataKeybCmd.ID_DEFAULT_LAYER)
        data.append(min(layer, self.num_layers() - 1))
        self.send_sysex(QMKataKeybCmd.SET, data)

    def keyb_set_macwin_mode(self, macwin_mode):
        self.dbg.tr("SYSEX_COMMAND", "keyb_set_macwin_mode: {}", macwin_mode)
        data = bytearray()
        data.append(QMKataKeybCmd.ID_MACWIN_MODE)
        data.append(ord(macwin_mode))
        self.send_sysex(QMKataKeybCmd.SET, data)

    def keyb_get_config(self, config_id=0):
        self.dbg.tr("SYSEX_COMMAND", "keyb_get_config: {}", config_id)
        if config_id == 0:
            for config_id in self.struct_layout[QMKataKeybCmd.ID_CONFIG]:
                self.send_sysex(QMKataKeybCmd.GET, [QMKataKeybCmd.ID_CONFIG, config_id])
        else:
            self.send_sysex(QMKataKeybCmd.GET, [QMKataKeybCmd.ID_CONFIG, config_id])

    def keyb_get_status(self, repeat_every_ms, status_id, from_timer=False):
        self.dbg.tr(
            "SYSEX_COMMAND",
            "keyb_get_status: {} every {} ms",
            status_id,
            repeat_every_ms,
        )

        if from_timer:
            repeat_every_ms = self.get_status_every_ms
        else:
            self.get_status_every_ms = repeat_every_ms

        if repeat_every_ms > 0:
            QtCore.QTimer.singleShot(
                repeat_every_ms,
                lambda: self.keyb_get_status(repeat_every_ms, status_id, True),
            )

        if status_id > 0:
            self.send_sysex(QMKataKeybCmd.GET, [QMKataKeybCmd.ID_STATUS, status_id])
        else:
            for _id in self.struct_layout[QMKataKeybCmd.ID_STATUS]:
                self.send_sysex(QMKataKeybCmd.GET, [QMKataKeybCmd.ID_STATUS, _id])

    def keyb_set_config(self, config):
        TYPE_BIT = self.keyboardModel.KeybStruct.TYPES["bit"]
        TYPE_UINT8 = self.keyboardModel.KeybStruct.TYPES["uint8"]
        TYPE_UINT16 = self.keyboardModel.KeybStruct.TYPES["uint16"]
        TYPE_UINT32 = self.keyboardModel.KeybStruct.TYPES["uint32"]
        TYPE_UINT64 = self.keyboardModel.KeybStruct.TYPES["uint64"]
        TYPE_FLOAT = self.keyboardModel.KeybStruct.TYPES["float"]
        TYPE_ARRAY = self.keyboardModel.KeybStruct.TYPES["array"]

        self.dbg.tr("SYSEX_COMMAND", "keyb_set_config: {}", config)
        try:
            config_id = config[0]
            field_values = config[1]
            config_layout = self.struct_layout[QMKataKeybCmd.ID_CONFIG][config_id]
            data = bytearray(self.MAX_LEN_SYSEX_DATA)
            data[0] = QMKataKeybCmd.ID_CONFIG
            data[1] = config_id
            for field_id, field in config_layout.items():
                field_type = field[0]
                field_offset = field[1]
                field_size = field[2]
                value = int(field_values[field_id])
                off = 2 + field_offset
                if field_type == TYPE_BIT:
                    off = 2 + field_offset // 8
                    field_offset = field_offset % 8
                    if field_size == 1:
                        if value:
                            data[off] |= 1 << field_offset
                        else:
                            data[off] &= ~(1 << field_offset)
                    else:
                        data[off] &= ~(bits_mask(field_size) << field_offset)
                        data[off] |= (value & bits_mask(field_size)) << field_offset
                elif field_type == TYPE_UINT8:  # todo: test and remove unused types
                    struct.pack_into(self.pack_endian + "B", data, off, value)
                elif field_type == TYPE_UINT16:
                    struct.pack_into(self.pack_endian + "H", data, off, value)
                elif field_type == TYPE_UINT32:
                    struct.pack_into(self.pack_endian + "I", data, off, value)
                elif field_type == TYPE_UINT64:
                    struct.pack_into(self.pack_endian + "Q", data, off, value)
                elif field_type == TYPE_FLOAT:
                    value = float(field_values[field_id])
                    struct.pack_into(self.pack_endian + "f", data, off, value)
                elif field_type == TYPE_ARRAY:
                    data[off : off + field_size] = value
                else:
                    value = 0
                self.dbg.tr(
                    "SYSEX_COMMAND",
                    "config[{config_id}][{field_id}]: {value}",
                    config_id,
                    field_id,
                    value,
                )
                if off >= len(data):
                    break
            data = data[: off + 1]
            self.send_sysex(QMKataKeybCmd.SET, data)
        except Exception as e:
            self.dbg.tr("E", f"keyb_set_config: {e}")
            return

    def keyb_set_dynld_function(self, fun_id, buf):
        if self.dbg.enabled("SYSEX_COMMAND"):
            self.dbg.tr(
                "SYSEX_COMMAND", "keyb_set_dynld_function: {} {}", fun_id, buf.hex(" ")
            )

        def dynld_fun_data_hdr(fun_id, offset):
            data = bytearray()
            data.append(QMKataKeybCmd.ID_DYNLD_FUNCTION)
            id_packed = struct.pack(self.pack_endian + "H", fun_id)
            offset_packed = struct.pack(self.pack_endian + "H", offset)
            data.extend(id_packed)
            data.extend(offset_packed)
            return data

        data = dynld_fun_data_hdr(fun_id, 0)
        data_hdr_len = len(data)
        i = 0
        while i < len(buf):
            if len(data) >= self.MAX_LEN_SYSEX_DATA:
                if not (response := self.send_sysex_wait(QMKataKeybCmd.SET, data)):
                    self.dbg.tr("E", "keyb_set_dynld_function: send failed")
                    return
                if response[1] != 0:
                    self.dbg.tr(
                        "E", "keyb_set_dynld_function: error returned {}", response[1]
                    )
                    return
                data = dynld_fun_data_hdr(fun_id, i)

            data.append(buf[i])
            i += 1

        if len(data) > data_hdr_len:
            if not (response := self.send_sysex_wait(QMKataKeybCmd.SET, data)):
                self.dbg.tr("E", "keyb_set_dynld_function: send failed")
                return
            if response[1] != 0:
                self.dbg.tr(
                    "E", "keyb_set_dynld_function: error returned {}", response[1]
                )
                return

        # last send for end of data, set function ptr
        data = dynld_fun_data_hdr(fun_id, 0xFFFF)
        self.send_sysex(QMKataKeybCmd.SET, data)

    def keyb_set_dynld_funexec(self, fun_id, buf=bytearray()):
        self.dbg.tr(
            "SYSEX_COMMAND", "keyb_set_dynld_funexec: {} {}", fun_id, buf.hex(" ")
        )

        data = bytearray()
        data.append(QMKataKeybCmd.ID_DYNLD_FUNEXEC)
        id = [fun_id & 0xFF, (fun_id >> 8) & 0xFF]
        data.extend(id)
        if buf:
            data.extend(buf)
        self.send_sysex(QMKataKeybCmd.SET, data)

        reponse = None
        timed_out = False
        start = time.monotonic()
        while not reponse and not timed_out:
            time.sleep(self.keyb_poll_time * 2)
            try:
                reponse = self.sysex_response[QMKataKeybCmd.ID_DYNLD_FUNEXEC]
                del self.sysex_response[QMKataKeybCmd.ID_DYNLD_FUNEXEC]
            except:
                timed_out = time.monotonic() - start > self.keyb_poll_time * 100
        return reponse

    def keyb_set_combo(self, slot, keys, keycode):
        self.dbg.tr(
            "SYSEX_COMMAND",
            "keyb_set_combo: slot={}, keys={}, keycode={}",
            slot,
            keys,
            keycode,
        )
        data = bytearray()
        data.append(QMKataKeybCmd.ID_COMBO)
        data.append(slot & 0xFF)
        for k in keys:
            data.extend(struct.pack(self.pack_endian + "H", k))
        # Padding if keys < 8
        if len(keys) < 8:
            data.extend(bytearray((8 - len(keys)) * 2))
        data.extend(struct.pack(self.pack_endian + "H", keycode))
        self.send_sysex(QMKataKeybCmd.SET, data)

    def keyb_get_combo(self, slot):
        self.dbg.tr("SYSEX_COMMAND", "keyb_get_combo: slot={}", slot)
        data = bytearray([QMKataKeybCmd.ID_COMBO, slot & 0xFF])
        self.send_sysex(QMKataKeybCmd.GET, data)

    def keyb_get_tap_dance(self, slot):
        """Fire-and-forget GET for one tap dance slot. Response arrives via signal_tap_dance."""
        self.dbg.tr("SYSEX_COMMAND", "keyb_get_tap_dance: slot={}", slot)
        buf = bytes([slot & 0xFF])
        self.send_sysex(QMKataKeybCmd.GET, bytes([QMKataKeybCmd.ID_TAP_DANCE]) + buf)

    def keyb_set_tap_dance(self, slot, kc1, kc2, kc3, hold):
        """SET tap dance slot and save to EEPROM."""
        self.dbg.tr(
            "SYSEX_COMMAND",
            "keyb_set_tap_dance: slot={}, kc1={}, kc2={}, kc3={}, hold={}",
            slot,
            kc1,
            kc2,
            kc3,
            hold,
        )
        payload = struct.pack(self.pack_endian + "BHHHH", slot, kc1, kc2, kc3, hold)
        self.send_sysex(
            QMKataKeybCmd.SET, bytes([QMKataKeybCmd.ID_TAP_DANCE]) + payload
        )

    def keyb_get_leader(self, slot):
        """Fire-and-forget GET for one leader slot. Response arrives via signal_leader."""
        self.dbg.tr("SYSEX_COMMAND", "keyb_get_leader: slot={}", slot)
        buf = bytes([slot & 0xFF])
        self.send_sysex(QMKataKeybCmd.GET, bytes([QMKataKeybCmd.ID_LEADER]) + buf)

    def keyb_set_leader(self, slot, seq, keycode):
        """SET leader slot: seq is list of up to 5 keycodes, keycode is the action."""
        self.dbg.tr(
            "SYSEX_COMMAND",
            "keyb_set_leader: slot={}, seq={}, keycode={}",
            slot,
            seq,
            keycode,
        )
        payload = struct.pack(self.pack_endian + "B", slot)
        for i in range(5):
            kc = seq[i] if i < len(seq) else 0
            payload += struct.pack(self.pack_endian + "H", kc)
        payload += struct.pack(self.pack_endian + "H", keycode)
        self.send_sysex(QMKataKeybCmd.SET, bytes([QMKataKeybCmd.ID_LEADER]) + payload)

    def keyb_set_module(self, slot_id, buf):
        """Upload module binary to keyboard slot via chunked SysEx.

        Wire format per chunk (after SysEx framing):
            [ID_MODULE, slot, off_lo, off_hi, declared_len, payload...]
        `declared_len` is the exact number of payload bytes in the chunk and
        lets the firmware ignore any trailing SysEx terminator / HID report
        padding that follows the logical message on the wire.

        Finalize: `[ID_MODULE, slot, 0xFF, 0xFF, 0x00]` (no payload).
        """
        if self.dbg.enabled("SYSEX_COMMAND"):
            self.dbg.tr("SYSEX_COMMAND", "keyb_set_module: slot={} len={}", slot_id, len(buf))

        # 5 header bytes consumed per chunk; rest is payload.
        MAX_PAYLOAD = self.MAX_LEN_SYSEX_DATA - 5
        if MAX_PAYLOAD <= 0:
            self.dbg.tr("E", "keyb_set_module: MAX_LEN_SYSEX_DATA too small")
            return False

        def chunk_header(slot_id, offset, declared_len):
            data = bytearray()
            data.append(QMKataKeybCmd.ID_MODULE)
            data.append(slot_id & 0xFF)
            data.extend(struct.pack("<H", offset))
            data.append(declared_len & 0xFF)
            return data

        offset = 0
        while offset < len(buf):
            chunk = buf[offset : offset + MAX_PAYLOAD]
            data = chunk_header(slot_id, offset, len(chunk))
            data.extend(chunk)
            if not (response := self.send_sysex_wait(QMKataKeybCmd.SET, data)):
                self.dbg.tr("E", "keyb_set_module: send failed at offset {}", offset)
                return False
            if response[1] != 0:
                self.dbg.tr("E", "keyb_set_module: error {} at offset {}", response[1], offset)
                return False
            offset += len(chunk)

        # Finalize: offset=0xFFFF signals end-of-data + commit to flash.
        # Use a generous timeout because module_load() may erase the
        # sector (~200 ms–1 s) if it isn't already blank.
        data = chunk_header(slot_id, 0xFFFF, 0)
        if not (response := self.send_sysex_wait(QMKataKeybCmd.SET, data, timeout_s=3.0)):
            self.dbg.tr("E", "keyb_set_module: finalize send failed")
            return False
        if response[1] != 0:
            self.dbg.tr("E", "keyb_set_module: finalize error {}", response[1])
            return False
        return True

    def keyb_get_module_summary(self):
        """Request summary of all module slots. Response via signal_module_status."""
        self.dbg.tr("SYSEX_COMMAND", "keyb_get_module_summary")
        data = bytearray([QMKataKeybCmd.ID_MODULE, 0xFF])
        self.send_sysex(QMKataKeybCmd.GET, data)

    def keyb_get_module(self, slot_id):
        """Request details of a specific module slot. Response via signal_module_status."""
        self.dbg.tr("SYSEX_COMMAND", "keyb_get_module: slot={}", slot_id)
        data = bytearray([QMKataKeybCmd.ID_MODULE, slot_id & 0xFF])
        self.send_sysex(QMKataKeybCmd.GET, data)

    def keyb_del_module(self, slot_id):
        """Unload module from slot. Returns True on success."""
        self.dbg.tr("SYSEX_COMMAND", "keyb_del_module: slot={}", slot_id)
        data = bytearray([QMKataKeybCmd.ID_MODULE, slot_id & 0xFF])
        if not (response := self.send_sysex_wait(QMKataKeybCmd.DEL, data)):
            self.dbg.tr("E", "keyb_del_module: send failed")
            return False
        if response[1] != 0:
            self.dbg.tr("E", "keyb_del_module: error {}", response[1])
            return False
        return True

    # -----------------------------------------------------------------------
    # Sector-preserving module reload helpers
    # -----------------------------------------------------------------------

    def keyb_read_module_magic(self, slot_id):
        """Read just the 4-byte magic word of a slot's header.

        Returns the uint32 magic, or None on failure. Used to skip blank
        slots (magic=0xFFFFFFFF) and invalidated slots (magic=0x00000000)
        during sector-preserving reload so we don't waste USB bandwidth
        reading 4 KB of 0xFF for empty slots.
        """
        data = bytearray([
            QMKataKeybCmd.ID_MODULE,
            slot_id & 0xFF,
            0x00, 0x00,  # offset = 0 (read first 4 bytes via chunked read)
        ])
        response = self.send_sysex_wait(QMKataKeybCmd.GET, data)
        if not response:
            return None
        # send_sysex_wait returns the tuple (True, stored_buf). For chunked
        # reads the stored_buf is the full response buffer (post seqnum strip).
        buf = response[1]
        # Response: [ID_MODULE, slot_id, off_lo, off_hi, chunk_len, data...]
        if len(buf) < 10 or buf[0] != QMKataKeybCmd.ID_MODULE:
            return None
        magic = buf[5] | (buf[6] << 8) | (buf[7] << 16) | (buf[8] << 24)
        return magic

    def keyb_read_module_binary(self, slot_id, size=0x1000):
        """Read full module binary from a slot via chunked GET.

        Returns bytes (size bytes) or None on failure.
        Wire format per chunk request:
            [ID_MODULE, slot_id, off_lo, off_hi]
        Response per chunk (distinguished from per-slot header by length):
            [ID_MODULE, slot_id, off_lo, off_hi, chunk_len, data...]
        """
        self.dbg.tr("SYSEX_COMMAND", "keyb_read_module_binary: slot={} size={}", slot_id, size)
        result = bytearray()

        offset = 0
        while offset < size:
            data = bytearray([
                QMKataKeybCmd.ID_MODULE,
                slot_id & 0xFF,
                offset & 0xFF,
                (offset >> 8) & 0xFF,
            ])
            response = self.send_sysex_wait(QMKataKeybCmd.GET, data)
            if not response:
                self.dbg.tr("E", "keyb_read_module_binary: GET failed at offset {}", offset)
                return None
            # response is (True, stored_buf); stored_buf is full response
            # after seqnum strip: [ID_MODULE, slot_id, off_lo, off_hi, chunk_len, data...]
            buf = response[1]
            if len(buf) < 6 or buf[0] != QMKataKeybCmd.ID_MODULE:
                self.dbg.tr("E", "keyb_read_module_binary: bad response at offset {}", offset)
                return None
            resp_slot = buf[1]
            resp_off = buf[2] | (buf[3] << 8)
            resp_len = buf[4]
            resp_data = buf[5:5+resp_len]
            if resp_slot != slot_id or resp_off != offset or len(resp_data) < resp_len:
                self.dbg.tr("E", "keyb_read_module_binary: slot/offset mismatch slot={} off={} exp=({},{})",
                             resp_slot, resp_off, slot_id, offset)
                return None
            result.extend(resp_data[:resp_len])
            offset += resp_len

        return bytes(result)

    def keyb_erase_module_sector(self, sector_id):
        """Erase an entire module flash sector (16 KB).

        sector_id: 0 = Sector 2 (slots 0-3), 1 = Sector 3 (slots 4-7).
        Returns True on success.

        Wire: SET [ID_MODULE, 0xFE, sector_id, 0x00, 0x00, 0x00]

        STM32F4 16 KB sector erase takes ~200 ms–1 s. Pass a generous
        per-attempt timeout so send_sysex_wait doesn't spuriously retry
        while the firmware is still busy with the erase.
        """
        self.dbg.tr("SYSEX_COMMAND", "keyb_erase_module_sector: sector={}", sector_id)
        data = bytearray([
            QMKataKeybCmd.ID_MODULE,
            0xFE,                   # special slot_id = sector erase
            0x00,                   # offset lo
            sector_id & 0xFF,       # offset hi → firmware reads sector_id here
            0x00,                   # declared_len = 0
        ])
        if not (response := self.send_sysex_wait(QMKataKeybCmd.SET, data, timeout_s=3.0)):
            self.dbg.tr("E", "keyb_erase_module_sector: send failed")
            return False
        if response[1] != 0:
            self.dbg.tr("E", "keyb_erase_module_sector: error {}", response[1])
            return False
        return True

    def keyb_sector_reload(self, slot_id, sector_binaries):
        """Reload an entire module sector, preserving sibling modules.

        slot_id: target slot being updated (0-7).
        sector_binaries: dict {slot_id: bytes} for slots that should be
            written. Missing entries (or entries with value None) are
            skipped — the sector erase already cleared them and leaving
            them blank (flash 0xFF) is correct. This avoids the "write
            4 KB of zeros" anti-pattern that would fail module_load()
            validation.

        Returns True on success.
        """
        sector_id = slot_id // 4
        sector_slots = [sector_id * 4 + i for i in range(4)]

        self.dbg.tr("SYSEX_COMMAND", "keyb_sector_reload: slot={} sector={} slots={}",
                     slot_id, sector_id, sector_slots)

        # Step 1: erase sector (firmware unloads all slots in sector)
        if not self.keyb_erase_module_sector(sector_id):
            return False

        # Step 2: write each slot individually (flash is already erased).
        # Slots not present in sector_binaries are left blank — this is
        # both faster (no USB traffic) and correct (module_load() rejects
        # all-zero headers, so we mustn't send them).
        for s in sector_slots:
            binary = sector_binaries.get(s)
            if binary is None:
                continue
            if not self.keyb_set_module(s, binary):
                self.dbg.tr("E", "keyb_sector_reload: failed writing slot {}", s)
                # Clear the firmware's erase-skip flag even on failure so a
                # later retry or independent load erases normally. Without
                # this, a stale flag would cause the next load to skip the
                # erase and corrupt data (flash can't program 0→1).
                self.keyb_sector_reload_done()
                return False

        # Signal firmware that sector-preserving reload is complete.
        # This clears the erase-skip flag so the next independent load
        # to the same sector will erase normally.
        self.keyb_sector_reload_done()

        return True

    def keyb_sector_reload_done(self):
        """Tell firmware that sector-preserving reload is complete.

        Clears the firmware's erase-skip flag so the next independent
        module load erases the sector normally. Wire: DEL [ID_MODULE, 0xFD].
        """
        self.dbg.tr("SYSEX_COMMAND", "keyb_sector_reload_done")
        data = bytearray([
            QMKataKeybCmd.ID_MODULE,
            0xFD,                   # special slot_id = reload done
        ])
        self.send_sysex_wait(QMKataKeybCmd.DEL, data)
