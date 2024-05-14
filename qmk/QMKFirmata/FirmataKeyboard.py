from PySide6 import QtCore
from PySide6.QtCore import Signal
from PySide6.QtGui import QImage, QColor, QPainter

import pyfirmata2, hid, serial, time, numpy as np
import glob, inspect, os, importlib.util, struct
from pathlib import Path
import keyboard, sched, threading, re

from DebugTracer import DebugTracer

#todo: add license
# this program is like a box of bugs, you never know what you're gonna get

#-------------------------------------------------------------------------------
#region list com ports
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
#endregion

#region combine images
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
            r = min(r1 + r2, FirmataKeyboard.MAX_RGB_VAL)
            g = min(g1 + g2, FirmataKeyboard.MAX_RGB_VAL)
            b = min(b1 + b2, FirmataKeyboard.MAX_RGB_VAL)
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
#endregion

def bits_mask(len):
    return (1 << len) - 1

#-------------------------------------------------------------------------------
FIRMATA_MSG = 0xFA
QMK_RAW_USAGE_PAGE = 0xFF60
QMK_RAW_USAGE_ID = 0x61

class SerialRawHID(serial.SerialBase):

    def __init__(self, vid, pid, epsize=64, timeout=100):
        self.dbg = DebugTracer(print=1, trace=1, obj=self)
        self.vid = vid
        self.pid = pid
        self.epsize = epsize
        self.timeout = timeout
        self.hid_device = None
        self._port = "{:04x}:{:04x}".format(vid, pid)
        self.open()

    def _reconfigure_port(self):
        pass

    def __str__(self) -> str:
        return "RAWHID: vid={:04x}, pid={:04x}".format(self.vid, self.pid)

    def _read_msg(self):
        try:
            data = bytearray(self.hid_device.read(self.epsize, self.timeout))
            # todo may strip trailing zeroes after END_SYSEX
            #data = data.rstrip(bytearray([0])) # remove trailing zeros
            #if len(data) > 0:
                #self.dbg.tr(f"rawhid read:{data.hex(' ')}")
        except Exception as e:
            data = bytearray()

        if len(data) == 0:
            #self.data.append(0) # dummy data to feed firmata
            return

        if data[0] == FIRMATA_MSG:
            data.pop(0)
        self.data.extend(data)

    def inWaiting(self):
        if len(self.data) == 0:
            self._read_msg()
        return len(self.data)

    def open(self):
        try:
            device_list = hid.enumerate(self.vid, self.pid)
            device = None
            for _device in device_list:
                #self.dbg.tr(f"found hid device: {_device}")
                if _device['usage_page'] == QMK_RAW_USAGE_PAGE: # 'usage' should be QMK_RAW_USAGE_ID
                    self.dbg.tr(f"found qmk raw hid device: {_device}")
                    device = _device
                    break

            if not device:
                raise Exception("no raw hid device found")

            self.hid_device = hid.device()
            self.hid_device.open_path(device['path'])

            self.data = bytearray()
            self.write(bytearray([0x00, FIRMATA_MSG, 0xf0, 0x71, 0xf7]))
            #self._read_msg()
            #if len(self.data) == 0:
                #self.dbg.tr(f"no response from device")
        except Exception as e:
            self.hid_device = None
            raise serial.SerialException(f"Could not open HID device: {e}")

        self.dbg.tr(f"opened HID device: {self.hid_device}")

    def is_open(self):
        return self.hid_device != None

    def close(self):
        if self.hid_device:
            self.hid_device.close()
            self.hid_device = None

    def write(self, data):
        if not self.hid_device:
            raise serial.SerialException("device not open")

        data = bytearray([0x00, FIRMATA_MSG]) + data
        #print(f"rawhid write:{data.hex(' ')}")
        return self.hid_device.write(data)

    def read(self, size=1):
        if not self.hid_device:
            raise serial.SerialException("device not open")

        if len(self.data) == 0:
            self._read_msg()
        if len(self.data) > 0:
            #self.dbg.tr(f"read:{self.data[0]}")
            return chr(self.data.pop(0))

        self.dbg.tr(f"read: no data")
        return chr(0)

    def read_all(self):
        pass

    def read_until(self, expected=b'\n', size=None):
        pass

#-------------------------------------------------------------------------------
class DefaultKeyboardModel:
    RGB_MAXTRIX_W = 19
    RGB_MAXTRIX_H = 6
    NUM_RGB_LEDS = 110
    RGB_MAX_REFRESH = 5

    DEFAULT_LAYER = 2
    NUM_LAYERS = 8

    def __init__(self, name):
        self.name = name
        pass

    def xy_to_rgb_index(x, y):
        return y * DefaultKeyboardModel.RGB_MAXTRIX_W + x


class FirmataKeybCmd_v0_1:
    EXTENDED   = 0 # extended command
    SET        = 1 # set a value for 'ID_...'
    GET        = 2 # get a value for 'ID_...'
    ADD        = 3 # add a value to 'ID_...'
    DEL        = 4 # delete a value from 'ID_...'
    PUB        = 5 # battery status, mcu load, diagnostics, debug traces, ...
    SUB        = 6 # todo subscribe to for example battery status, mcu load, ...
    RESPONSE   = 0xf # response to a command
    #----------------------------------------------------
    ID_RGB_MATRIX_BUF   = 1
    ID_DEFAULT_LAYER    = 2
    ID_DEBUG_MASK       = 3
    ID_BATTERY_STATUS   = 4
    ID_MACWIN_MODE      = 5
    ID_RGB_MATRIX_MODE  = 6
    ID_RGB_MATRIX_HSV   = 7
    ID_DYNLD_FUNCTION   = 250 # dynamic loaded function
    ID_DYNLD_FUNEXEC    = 251 # execute dynamic loaded function

class FirmataKeybCmd_v0_2(FirmataKeybCmd_v0_1):
    ID_CLI                  = 3 # debug mask deprecated
    ID_STATUS               = 4 # status, follow up with status id
    ID_CONFIG_LAYOUT        = 8
    ID_CONFIG               = 9
    ID_KEYPRESS_EVENT       = 10

# todo: dictionary with version as key
FirmataKeybCmd = FirmataKeybCmd_v0_2

class FirmataKeyboard(pyfirmata2.Board, QtCore.QObject):
    """
    A keyboard which "talks" arduino firmata.
    """
    #-------------------------------------------------------------------------------
    # signal received qmk keyboard data
    signal_console_output = Signal(str)
    signal_macwin_mode = Signal(str)
    signal_default_layer = Signal(int)
    signal_config_model = Signal(object)
    signal_config = Signal(object)

    #-------------------------------------------------------------------------------
    MAX_RGB_VAL = 255
    # format: QImage.Format_RGB888 or QImage.Format_BGR888
    @staticmethod
    def pixel_to_rgb_index_duration(pixel, format, index, duration, brightness=(1.0,1.0,1.0)):
        if index < 0:
            return None
        ri = 0; gi = 1; bi = 2
        if format == QImage.Format_BGR888:
            ri = 2; bi = 0
        #print(brightness)
        data = bytearray()
        data.append(index)
        data.append(duration)
        data.append(min(int(pixel[ri]*brightness[ri]), FirmataKeyboard.MAX_RGB_VAL))
        data.append(min(int(pixel[gi]*brightness[gi]), FirmataKeyboard.MAX_RGB_VAL))
        data.append(min(int(pixel[bi]*brightness[bi]), FirmataKeyboard.MAX_RGB_VAL))
        return data

    @staticmethod
    def load_keyboard_models(path="keyboards"):
        keyb_models = {} # class name -> class
        keyb_models_vpid = {} # vid/pid -> class

        path = Path(os.path.dirname(__file__)).joinpath(path)
        glob_filter = os.path.join(path, '[!_]*.py')
        model_files = glob.glob(glob_filter)
        #print(model_files)
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

    RAW_EPSIZE_FIRMATA = 64 # 32
    MAX_LEN_SYSEX_DATA = 60

    class KeybCli:
        class DictOnReadWrite(dict):
            def __init__(self, kb_cli, on_read, on_write):
                self.kb_cli = kb_cli
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

        def __init__(self, keyboard):
            self.keyboard = keyboard
            self.m = self.DictOnReadWrite(self, self.on_mem_read, self.on_mem_write) # memory access
            self.e = self.DictOnReadWrite(self, self.on_eeprom_read, self.on_eeprom_write) # eeprom access
            self.fn = {} # function table, todo load map file

        def on_mem_read(self, key):
            try:
                addr = key[0]
                size = key[1]
            except:
                addr = key
                size = 1
            #print(f"on_mem_read: key={key}, addr={addr}, size={size}")
            resp = self.keyboard.keyb_set_cli_command(f"mr {hex(addr)} {size}")
            if size == 1:
                return resp[0]
            if size == 2:
                return struct.unpack_from('<H', resp)[0]
            if size == 4:
                return struct.unpack_from('<I', resp)[0]
            return resp

        def on_mem_write(self, key, val):
            try:
                addr = key[0]
                size = key[1]
            except:
                addr = key
                size = 1
            #print(f"on_mem_write: key={key}, addr={addr}, size={size}")
            resp = self.keyboard.keyb_set_cli_command(f"mw {hex(addr)} {size} {hex(val)}")

        def on_eeprom_read(self, key):
            if key == "l": # layout
                resp = self.keyboard.keyb_set_cli_command("el")
                return resp
            try:
                addr = key[0]
                size = key[1]
            except:
                addr = key
                size = 1
            #print(f"on_eeprom_read: key={key}, addr={addr}, size={size}")
            resp = self.keyboard.keyb_set_cli_command(f"er {hex(addr)} {size}")
            if size == 1:
                return resp[0]
            if size == 2:
                return struct.unpack_from('<H', resp)[0]
            if size == 4:
                return struct.unpack_from('<I', resp)[0]
            return resp

        def on_eeprom_write(self, key, val):
            try:
                addr = key[0]
                size = key[1]
            except:
                addr = key
                size = 1
            #print(f"on_eeprom_write: key={key}, addr={addr}, size={size}")
            resp = self.keyboard.keyb_set_cli_command(f"ew {hex(addr)} {size} {hex(val)}")

        def call(self, addr):
            resp = self.keyboard.keyb_set_cli_command(f"c {hex(addr)}")

        def set(self, key, val):
            print("todo")

        def get(self, key):
            print("todo")

    def __init__(self, *args, **kwargs):
        QtCore.QObject.__init__(self)
        #----------------------------------------------------
        #region debug tracers
        self.dbg_rgb_buf = 0
        self.dbg = {}
        self.dbg['ERROR']           = DebugTracer(print=1, trace=1, obj=self)
        self.dbg['DEBUG']           = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['CONSOLE']         = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['CLI']             = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['SYSEX_COMMAND']   = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['SYSEX_RESPONSE']  = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['SYSEX_PUB']       = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['RGB_BUF']         = DebugTracer(print=0, trace=1, obj=self)
        dbg = self.dbg['DEBUG']
        #endregion

        self.kb_cli = self.KeybCli(self)
        #----------------------------------------------------
        self.samplerThread = None

        self.img = {}   # sender -> rgb QImage
        self.img_ts_prev = 0 # previous image timestamp

        self.name = None
        self.port = None
        self.vid_pid = None
        for arg in kwargs:
            if arg == "name":
                self.name = kwargs[arg]
            if arg == "port":
                self.port = kwargs[arg]
            if arg == "vid_pid":
                self.vid_pid = kwargs[arg]

        if self.name == None:
            self.name = self.port

        self.port_type = "serial"

        # load "keyboard models", keyboard model contains name, vid/pid, rgb matrix size, ...
        self.keyboardModel, self.keyboardModelVidPid = self.load_keyboard_models()
        if dbg.print:
            for class_name, class_type in self.keyboardModel.items():
                dbg.tr(f"keyboard model: {class_name} ({hex(class_type.vid_pid()[0])}:{hex(class_type.vid_pid()[1])}), {class_type}")
            #for vid_pid, class_type in self.keyboardModelVidPid.items():
                #dbg.tr(f"vid pid: {vid_pid}, Class Type: {class_type}")

        if self.port == None and self.vid_pid:
            self.keyboardModel = self.keyboardModelVidPid[(self.vid_pid[0], self.vid_pid[1])]
            try:
                self.port_type = self.keyboardModel.PORT_TYPE
            except Exception as e:
                pass

            self.port = find_com_port(self.vid_pid[0], self.vid_pid[1])
            dbg.tr(f"using keyboard: {self.keyboardModel} on port {self.port}")
            self.name = self.keyboardModel.name()
            self._rgb_max_refresh = self.rgb_max_refresh()

        self.samplerThread = pyfirmata2.util.Iterator(self)

        if self.port_type == "rawhid":
            self.sp = SerialRawHID(self.vid_pid[0], self.vid_pid[1], self.RAW_EPSIZE_FIRMATA)
            self.MAX_LEN_SYSEX_DATA = self.RAW_EPSIZE_FIRMATA - 4
        else:
            self.sp = serial.Serial(self.port, 115200, timeout=1)

        # pretend its an arduino
        self._layout = pyfirmata2.BOARDS['arduino']
        if not self.name:
            self.name = self.port

    def __str__(self):
        return "{0.name} ({0.sp.port})".format(self)

    #-------------------------------------------------------------------------------
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
            self.dbg['DEBUG'].tr(f"default_layer: {e}")
        return DefaultKeyboardModel.DEFAULT_LAYER

    def xy_to_rgb_index(self, x, y):
        xy_to_rgb_index =  DefaultKeyboardModel.xy_to_rgb_index
        if self.keyboardModel:
            xy_to_rgb_index = self.keyboardModel.xy_to_rgb_index
        return xy_to_rgb_index(x, y)

    #-------------------------------------------------------------------------------
    def start(self):
        if self._layout:
            self.setup_layout(self._layout)
        else:
            self.auto_setup()

        self.keyb_cli_response = {}
        self.keyb_cli_seq = 0

        self.config_layout = {}
        self.config_model = None
        self.add_cmd_handler(pyfirmata2.STRING_DATA, self.console_line_handler)
        self.add_cmd_handler(FirmataKeybCmd.RESPONSE, self.sysex_response_handler)
        self.add_cmd_handler(FirmataKeybCmd.PUB, self.sysex_pub_handler)

        self.samplingOn()
        self.send_sysex(pyfirmata2.REPORT_FIRMWARE, [])
        self.send_sysex(pyfirmata2.REPORT_VERSION, [])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG_LAYOUT])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_MACWIN_MODE])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_STATUS])

        self.pack_endian = '<' # most likely little endian
        try:
            if self.keyboardModel.MCU[2].startswith("be"):
                self.pack_endian = '>' # big endian
        except:
            pass

        time.sleep(1)
        print("-"*80)
        print(f"{self}")
        print(f"qmk firmata version:{self.firmware} {self.firmware_version}, firmata={self.get_firmata_version()}")
        print(f"mcu:{self.keyboardModel.MCU} {self.pack_endian}")
        print("-"*80)

        self.key_machine = KeyMachine(self)
        try:
            for config_id in self.config_layout:
                self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG, config_id])
        except Exception as e:
            self.dbg['DEBUG'].tr(f"{e}")

        self.signal_config_model.emit(self.config_model)
        config_auto_update = False
        if config_auto_update and len(self.config_layout) > 0:
            self.timer_config_update = QtCore.QTimer(self)
            self.timer_config_update.timeout.connect(self.keyb_config)
            self.timer_config_update.start(500)

    def stop(self):
        try:
            self.sp.close()
        except Exception as e:
            self.dbg['ERROR'].tr(f"{e}")
        self.samplingOff()

    #-------------------------------------------------------------------------------
    def _sysex_data_to_bytearray(self, data):
        buf = bytearray()
        if len(data) % 2 != 0:
            self.dbg['ERROR'].tr(f"sysex_pub_handler: invalid data length {len(data)}")
            return buf
        for off in range(0, len(data), 2):
            # Combine two bytes
            buf.append(data[off+1] << 7 | data[off])
        return buf

    def sysex_pub_handler(self, *data):
        dbg = self.dbg['SYSEX_PUB']
        #dbg.tr(f"sysex_pub_handler: {data}")
        buf = self._sysex_data_to_bytearray(data)
        if dbg.print:
            dbg.tr("-"*40)
            dbg.tr(f"sysex pub:\n{buf.hex(' ')}")

        if buf[0] == FirmataKeybCmd.ID_KEYPRESS_EVENT:
            col = buf[1]
            row = buf[2]
            time = struct.unpack_from('<H', buf, 3)[0] # todo use self.pack_endian
            type = buf[5]
            pressed = buf[6]
            #dbg.tr(f"key press event: row={row}, col={col}, time={time}, type={type}, pressed={pressed}")
            if self.key_machine:
                self.key_machine.key_event(row, col, time, pressed)

    #-------------------------------------------------------------------------------
    def sysex_response_handler(self, *data):
        dbg = self.dbg['SYSEX_RESPONSE']
        #dbg.tr(f"sysex_response_handler: {data}")
        buf = self._sysex_data_to_bytearray(data)
        if dbg.print:
            dbg.tr("-"*40)
            dbg.tr(f"sysex response:\n{buf.hex(' ')}")

        if buf[0] == FirmataKeybCmd.ID_CLI:
            dbg.tr(f"cli response: {buf}")
            cli_seq = buf[1]
            buf.pop(0); buf.pop(0)
            self.keyb_cli_response[cli_seq] = buf
            return
        if buf[0] == FirmataKeybCmd.ID_MACWIN_MODE:
            macwin_mode = chr(buf[1])
            dbg.tr(f"macwin mode: {macwin_mode}")
            self.signal_macwin_mode.emit(macwin_mode)
            self.signal_default_layer.emit(self.default_layer(macwin_mode))
            return
        if buf[0] == FirmataKeybCmd.ID_STATUS:
            # todo
            battery_charging = buf[1]
            battery_level = buf[2]
            dbg.tr(f"battery charging: {battery_charging}, battery level: {battery_level}")
            return
        if buf[0] == FirmataKeybCmd.ID_CONFIG_LAYOUT:
            off = 1
            config_id = buf[off]; off += 1
            config_size = buf[off]; off += 1
            config_flags = buf[off]; off += 1
            dbg.tr(f"config id: {config_id}, size: {config_size}, flags: {config_flags}")
            config_fields = {}
            config_field = buf[off]
            while config_field != 0:
                field_type = buf[off+1]
                field_offset = buf[off+2]
                field_size = buf[off+3]
                config_fields[config_field] = (field_type, field_offset, field_size, config_flags)
                off += 4
                try:
                    config_field = buf[off]
                except:
                    break
            # config layout used to get/set of config field values in byte buffer
            self.config_layout[config_id] = config_fields
            if dbg.print:
                self.keyboardModel.keyb_config().print_config_layout(config_id, config_fields)
            self.config_model = self.keyboardModel.keyb_config().keyb_config_model(self.config_model, config_id, config_fields)
            return
        if buf[0] == FirmataKeybCmd.ID_CONFIG:
            TYPE_BIT = self.keyboardModel.keyb_config().TYPES["bit"]
            TYPE_UINT8 = self.keyboardModel.keyb_config().TYPES["uint8"]
            TYPE_UINT16 = self.keyboardModel.keyb_config().TYPES["uint16"]
            TYPE_UINT32 = self.keyboardModel.keyb_config().TYPES["uint32"]
            TYPE_UINT64 = self.keyboardModel.keyb_config().TYPES["uint64"]
            TYPE_FLOAT = self.keyboardModel.keyb_config().TYPES["float"]
            TYPE_ARRAY = self.keyboardModel.keyb_config().TYPES["array"]

            config_id = buf[1]
            config_fields = self.config_layout[config_id]
            off = 2
            field_values = {}
            for field_id, field in config_fields.items():
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
                        dbg.tr(f"config[{config_id}][{field_id}]:off={off}, offset={field_offset}, value={value}")
                    else:
                        value = (buf[off] >> field_offset) & bits_mask(field_size)
                elif field_type == TYPE_UINT8:
                    value = struct.unpack_from('<B', buf, off)[0]
                elif field_type == TYPE_UINT16: # todo: test uint16/32/64/float/array
                    #todo: big endian for uint16/32/64/float
                    value = struct.unpack_from('<H', buf, off)[0]
                elif field_type == TYPE_UINT32:
                    value = struct.unpack_from('<I', buf, off)[0]
                elif field_type == TYPE_UINT64:
                    value = struct.unpack_from('<Q', buf, off)[0]
                elif field_type == TYPE_FLOAT:
                    value = struct.unpack_from('<f', buf, off)[0]
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
                    value = buf[off:off+(field_size*item_type_size)]
                else:
                    value = 0
                field_values[field_id] = value
                dbg.tr(f"config[{config_id}][{field_id}]: {value}")
                if off >= len(buf):
                    break
            # signal to gui the config values
            self.signal_config.emit((config_id, field_values))
            return

    def console_line_handler(self, *data):
        #self.dbg['CONSOLE'].tr(f"console: {data}")
        if len(data) % 2 != 0:
            data = data[:-1 ]
        line = self._sysex_data_to_bytearray(data).decode('utf-8', 'ignore')
        if line:
            self.signal_console_output.emit(line)

    # todo: move from ui thread to separate thread/process
    def run_script(self, script, signal_output=None):
        from contextlib import redirect_stdout
        from io import StringIO
        class ScriptOutput(StringIO):
            def __init__(self, signal_output):
                self.signal_output = signal_output
                super().__init__()

            def write(self, string):
                if self.signal_output:
                    self.signal_output.emit(string)
                super().write(string)

        globals_dict = globals()
        globals_dict.update({ "kb": self.kb_cli })
        script_output = ScriptOutput(signal_output)
        with redirect_stdout(script_output):
            exec(script, globals_dict, {})

    #-------------------------------------------------------------------------------
    def keyb_set_cli_command(self, cmd):
        dbg = self.dbg['CLI']
        dbg.tr(f"keyb_set_cli_command: {cmd}")

        def cli_cmd_encode(cmd_str, endian):
            CLI_CMD_MEMORY      = 0x01
            CLI_CMD_EEPROM      = 0x02
            CLI_CMD_CALL        = 0x03
            CLI_CMD_LAYOUT      = 0x40
            CLI_CMD_WRITE       = 0x80
            try:
                cmd_args = cmd_str.strip().split(' ')
                cmd = cmd_args[0]
                if cmd[0] == 'm' or cmd[0] == 'e':
                    cli_cmd = CLI_CMD_MEMORY if cmd[0] == 'm' else CLI_CMD_EEPROM
                    if cmd[1] == 'l' and cli_cmd == CLI_CMD_EEPROM:
                        ba = bytearray([cli_cmd|CLI_CMD_LAYOUT])
                        return ba
                    if cmd[1] == 'r':
                        addr = int(cmd_args[1], 16)
                        size = int(cmd_args[2])
                        #print(f"cli_cmd_encode: {cli_cmd}, {addr}, {size}")
                        ba = bytearray([cli_cmd])
                        return ba + bytearray(struct.pack(endian+'I', addr)) + bytearray([size%256])
                    if cmd[1] == 'w':
                        addr = int(cmd_args[1], 16)
                        size = int(cmd_args[2])
                        val = int(cmd_args[3], 16)
                        #print(f"cli_cmd_encode: {cli_cmd}, {addr}, {size}, {val}")
                        ba = bytearray([cli_cmd|CLI_CMD_WRITE])
                        return ba + bytearray(struct.pack(endian+'I', addr)) + bytearray([size%256]) + bytearray(struct.pack(endian+'I', val))
                if cmd[0] == 'c':
                    addr = int(cmd_args[1], 16)
                    #print(f"cli_cmd_encode: {CLI_CMD_CALL}, {addr}")
                    return bytearray([CLI_CMD_CALL]) + bytearray(struct.pack(endian+'I', addr))
            except:
                return None

        cmd_ba = cli_cmd_encode(cmd, self.pack_endian)
        if dbg.print:
            dbg.tr(f"keyb_set_cli_command: cmd_ba: {cmd_ba.hex(' ')}")

        cli_seq = self.keyb_cli_seq % 256
        self.keyb_cli_seq += 1
        data = bytearray()
        data.append(FirmataKeybCmd.ID_CLI)
        data.append(cli_seq)
        data.extend(cmd_ba)
        self.send_sysex(FirmataKeybCmd.SET, data)

        # todo: wait for response
        wait_for_response = True
        response = None
        if wait_for_response:
            keyb_poll_time = 1/1000
            timed_out = False
            start = time.monotonic()
            while response == None and not timed_out:
                time.sleep(keyb_poll_time*2)
                try:
                    response = self.keyb_cli_response[cli_seq]
                    del self.keyb_cli_response[cli_seq]
                except:
                    timed_out = time.monotonic() - start > keyb_poll_time * 100

            if dbg.print:
                response_str = "none"
                if response:
                    response_str = response.hex(' ')
                dbg.tr(f"keyb_set_cli_command: response: {response_str}")
        return response

    def keyb_set_rgb_buf(self, img, rgb_multiplier):
        if self.dbg_rgb_buf:
            self.dbg['RGB_BUF'].tr("-"*120)
            self.dbg['RGB_BUF'].tr(f"rgb mult {rgb_multiplier}")

        #self.dbg['DEBUG'].tr(f"rgb img from sender {self.sender()} {img}")
        if not img:
            self.dbg['DEBUG'].tr(f"rgb sender {self.sender()} stopped")
            if self.sender() in self.img:
                self.img.pop(self.sender())
            return

        # multiple images senders -> combine images
        combined_img = img
        #prev_img = self.img[self.sender()]
        if len(self.img) > 1:
            combined_img = img.copy()
            for key in self.img:
                if key != self.sender():
                    #self.dbg['DEBUG'].tr(f"combine image from {key}")
                    combined_img = combine_qimages(combined_img, self.img[key])
        #if not self.sender() in self.img:
            #self.dbg['DEBUG'].tr(f"new sender {self.sender()} {img}")
        self.img[self.sender()] = img
        img = combined_img
        # max refresh
        if time.monotonic() - self.img_ts_prev < 1/self._rgb_max_refresh:
            #print("skip")
            return
        self.img_ts_prev = time.monotonic()

        #-------------------------------------------------------------------------------
        # iterate through the image pixels and convert to "keyboard rgb pixels" and send to keyboard
        height = img.height()
        width = img.width()
        arr = np.ndarray((height, width, 3), buffer=img.constBits(), strides=[img.bytesPerLine(), 3, 1], dtype=np.uint8)

        img_format = img.format()
        RGB_PIXEL_SIZE = 5
        num_sends = 0
        data = bytearray()
        data.append(FirmataKeybCmd.ID_RGB_MATRIX_BUF)
        for y in range(height):
            for x in range(width):
                pixel = arr[y, x]
                rgb_pixel = self.pixel_to_rgb_index_duration(pixel, img_format, self.xy_to_rgb_index(x, y), 50, rgb_multiplier)
                if rgb_pixel:
                    data.extend(rgb_pixel)

                if self.dbg_rgb_buf:
                    self.dbg['RGB_BUF'].tr(f"{x:2},{y:2}=({pixel[0]:3},{pixel[1]:3},{pixel[2]:3})", end=" ")
                    self.dbg['RGB_BUF'].tr(rgb_pixel.hex(' '))

                if len(data) + RGB_PIXEL_SIZE > self.MAX_LEN_SYSEX_DATA:
                    self.send_sysex(FirmataKeybCmd.SET, data)
                    num_sends += 1
                    # todo sync with keyboard to avoid buffer overflow
                    # rawhid may use smaller epsize so sleep after more sends
                    if self.port_type == "rawhid":
                        if num_sends % 10 == 0:
                            time.sleep(0.002)
                    else:
                        if num_sends % 2 == 0:
                            time.sleep(0.002)

                    data = bytearray()
                    data.append(FirmataKeybCmd.ID_RGB_MATRIX_BUF)

        if len(data) > 0:
            self.send_sysex(FirmataKeybCmd.SET, data)
            num_sends += 1
        #time.sleep(0.005)

    def keyb_set_default_layer(self, layer):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_default_layer: {layer}")
        data = bytearray()
        data.append(FirmataKeybCmd.ID_DEFAULT_LAYER)
        data.append(min(layer, self.num_layers()-1))
        self.send_sysex(FirmataKeybCmd.SET, data)

    def keyb_set_macwin_mode(self, macwin_mode):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_macwin_mode: {macwin_mode}")
        data = bytearray()
        data.append(FirmataKeybCmd.ID_MACWIN_MODE)
        data.append(ord(macwin_mode))
        self.send_sysex(FirmataKeybCmd.SET, data)

    def keyb_get_config(self, config_id = 0):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_get_config: {config_id}")
        if config_id == 0:
            for config_id in self.config_layout:
                self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG, config_id])
        else:
            self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG, config_id])

    def keyb_set_config(self, config):
        TYPE_BIT = self.keyboardModel.keyb_config().TYPES["bit"]
        TYPE_UINT8 = self.keyboardModel.keyb_config().TYPES["uint8"]
        TYPE_UINT16 = self.keyboardModel.keyb_config().TYPES["uint16"]
        TYPE_UINT32 = self.keyboardModel.keyb_config().TYPES["uint32"]
        TYPE_UINT64 = self.keyboardModel.keyb_config().TYPES["uint64"]
        TYPE_FLOAT = self.keyboardModel.keyb_config().TYPES["float"]
        TYPE_ARRAY = self.keyboardModel.keyb_config().TYPES["array"]

        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_config: {config}")
        try:
            config_id = config[0]
            field_values = config[1]
            config_layout = self.config_layout[config_id]
            data = bytearray(self.MAX_LEN_SYSEX_DATA)
            data[0] = FirmataKeybCmd.ID_CONFIG
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
                            data[off] |= (1 << field_offset)
                        else:
                            data[off] &= ~(1 << field_offset)
                    else:
                        data[off] &= ~(bits_mask(field_size) << field_offset)
                        data[off] |= (value & bits_mask(field_size)) << field_offset
                elif field_type == TYPE_UINT8:
                    struct.pack_into('<B', data, off, value)
                elif field_type == TYPE_UINT16:
                    struct.pack_into('<H', data, off, value)
                elif field_type == TYPE_UINT32:
                    struct.pack_into('<I', data, off, value)
                elif field_type == TYPE_UINT64: # todo: remove unused types
                    struct.pack_into('<Q', data, off, value)
                elif field_type == TYPE_FLOAT:
                    value = float(field_values[field_id])
                    struct.pack_into('<f', data, off, value)
                elif field_type == TYPE_ARRAY:
                    #todo: field_values[field_id] to bytearray
                    data[off:off+field_size] = value
                else:
                    value = 0
                dbg.tr(f"config[{config_id}][{field_id}]: {value}")
                if off >= len(data):
                    break
            self.send_sysex(FirmataKeybCmd.SET, data)
        except Exception as e:
            self.dbg['ERROR'].tr(f"keyb_set_config: {e}")
            return

    def keyb_set_dynld_function(self, fun_id, buf):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_dynld_function: {fun_id} {buf.hex(' ')}")
        data = bytearray()
        data.append(FirmataKeybCmd.ID_DYNLD_FUNCTION)
        id = [fun_id & 0xff, (fun_id >> 8) & 0xff]
        offset = [0, 0]
        data.extend(id)
        data.extend(offset)

        num_sends = 0
        i = 0
        while i < len(buf):
            if len(data) >= self.MAX_LEN_SYSEX_DATA:
                self.send_sysex(FirmataKeybCmd.SET, data)
                num_sends += 1
                # todo: sync with keyboard to avoid firmata buffer overflow
                if num_sends % 2 == 0:
                    time.sleep(0.002)

                data = bytearray()
                data.append(FirmataKeybCmd.ID_DYNLD_FUNCTION)
                offset = [i & 0xff, (i >> 8) & 0xff]
                data.extend(id)
                data.extend(offset)

            data.append(buf[i])
            i += 1

        if len(data) > 0:
            self.send_sysex(FirmataKeybCmd.SET, data)

        data = bytearray()
        data.append(FirmataKeybCmd.ID_DYNLD_FUNCTION)
        offset = [0xff, 0xff]
        data.extend(id)
        data.extend(offset)
        self.send_sysex(FirmataKeybCmd.SET, data)

        # todo define DYNLD_... function ids
        DYNLD_TEST_FUNCTION = 1
        if fun_id == DYNLD_TEST_FUNCTION:
            self.keyb_set_dynld_funexec(fun_id)

    def keyb_set_dynld_funexec(self, fun_id, buf=bytearray()):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_dynld_funexec: {fun_id} {buf.hex(' ')}")

        data = bytearray()
        data.append(FirmataKeybCmd.ID_DYNLD_FUNEXEC)
        id = [fun_id & 0xff, (fun_id >> 8) & 0xff]
        data.extend(id)
        if buf:
            data.extend(buf)
        self.send_sysex(FirmataKeybCmd.SET, data)


#-------------------------------------------------------------------------------
# todo: move to separate file

class KeyMachine:

    def __init__(self, keyb):
        self.dbg = {}
        self.dbg['DEBUG']   = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['REPEAT']  = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['COMBO']   = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['SEQ']     = DebugTracer(print=0, trace=1, obj=self)
        self.dbg['MORSE']   = DebugTracer(print=1, trace=1, obj=self)

        self.dbg['DEBUG'].tr(f"KeyMachine: {keyb}")
        self.keyb = keyb
        try:
            self.key_layout = keyb.keyboardModel.KEY_LAYOUT['win']
        except:
            self.key_layout = None
        self.key_event_stack = [] #todo remove if not needed
        self.key_pressed = {}
        self.combos = {}
        self.sequences = {}

        self.key_repeat_delay = 0.5
        self.key_repeat_time = 0.05
        self.key_repeat_scheduler = sched.scheduler(time.time, time.sleep)
        self.key_repeat_sched_event = None

        self.sequence_handler_scheduler = sched.scheduler(time.time, time.sleep)
        self.sequence_handler_sched_event = None

        self.morse_handler_scheduler = sched.scheduler(time.time, time.sleep)
        self.morse_handler_sched_event = None
        self.morse_tap_stack = []

        try:
            #from pysinewave import SineWave
            self.morse_beep = SineWave(pitch = 14, pitch_per_second = 10, decibels=-200, decibels_per_second=10000)
            self.morse_beep.play()
        except:
            self.morse_beep = None

        devel_test = True
        if devel_test:
            def on_test_combo1():
                keyboard.write(u"hello äçξضяשå両めษᆆऔጩᗗ¿")

            def on_test_combo_leader():
                keyboard.write("leader key todo")

            def on_test_sequence():
                keyboard.write("hello hello hello")

            def on_windows_lock():
                os.system("rundll32.exe user32.dll,LockWorkStation")

            def on_test_sequence_1():
                keyboard.write("pam pam")

            def on_test_sequence_tap_1():
                keyboard.write("1st tap")
            def on_test_sequence_tap_2():
                keyboard.write("2nd tap")
            def on_test_sequence_tap_4():
                keyboard.write("all tapped!")

            self.register_combo(['left ctrl','left menu','space','m'], on_test_combo1)
            self.register_combo(['fn',';'], on_test_combo_leader)
            self.register_combo(['left windows','l'], on_windows_lock)

            self.register_sequence(['1','2','3'], [(0,300), (0,300)], on_test_sequence)
            self.register_sequence(['pause','pause','pause','pause'], [(0,300), (0,300), (0,300)], [ on_test_sequence_tap_1, on_test_sequence_tap_2, None, on_test_sequence_tap_4])
            self.register_sequence(['right','right','right','right','right'], [(350,500), (100,250), (100,250), (300,450)], on_test_sequence_1)

    def control_pressed(self):
        return self.key_pressed.get('left ctrl', 0) or self.key_pressed.get('ctrl', 0)

    def shift_pressed(self):
        return self.key_pressed.get('left shift', 0) or self.key_pressed.get('right shift', 0)

    def alt_pressed(self):
        return self.key_pressed.get('left menu', 0) or self.key_pressed.get('right menu', 0)

    def win_pressed(self):
        return self.key_pressed.get('left windows', 0) or self.key_pressed.get('right windows', 0)

    def fn_pressed(self):
        return self.key_pressed.get('fn', 0)

    def is_mod_key(self, key):
        return key.endswith('ctrl') or key.endswith('shift') or key.endswith('menu') or key.endswith('windows') or key == 'fn'

    def mod_keys_pressed(self):
        pressed = []
        if self.win_pressed():
            pressed.append('left windows')
        if self.alt_pressed():
            pressed.append('alt')
        if self.control_pressed():
            pressed.append('ctrl')
        if self.shift_pressed():
            pressed.append('shift')
        if self.fn_pressed():
            pressed.append('fn')
        return pressed

    def register_combo(self, keys, handler):
        combo_keys = "+".join(keys)
        self.combos[combo_keys] = (keys, handler)
        self.dbg['COMBO'].tr(f"register_combo: {combo_keys}, {keys}, {handler}")

    # todo: flags/options[] to define behavior for different "sequence types" (leader key, tap dance, ...)
    # - can define state change on key press/hold/release on each "sequence step"
    def register_sequence(self, keys, timeout, handler, flags=[]):
        sequence_keys = "+".join(keys)
        self.sequences[sequence_keys] = (keys, timeout, (0, 0), handler, flags) # sequence state: (index, time)
        self.dbg['SEQ'].tr(f"register_sequence: {sequence_keys}, {keys}, {timeout}, {handler}, {flags}")

    @staticmethod
    def time_elapsed(time_begin, time_end):
        time_diff = time_end - time_begin
        if time_diff < 0:
            time_diff = 65536 + time_diff
        return time_diff

    # todo: leader key, tap dance, ...
    def process_sequences(self, key, time, pressed):
        if pressed:
            for _key, seq_handler in self.sequences.items():
                sequence_keys = seq_handler[0]
                timeout = seq_handler[1]
                state = seq_handler[2]
                handler = seq_handler[3]
                state_index = state[0]
                state_time = state[1]
                try:
                    if key == sequence_keys[state_index]:
                        self.dbg['SEQ'].tr(f"process_sequences: {key}, {sequence_keys}, {state}")
                        if state_index > 0:
                            time_diff = self.time_elapsed(state_time, time)
                            if time_diff > timeout[state_index-1][1] or time_diff < timeout[state_index-1][0]:
                                self.dbg['SEQ'].tr(f"process_sequences: keypress time: {time_diff} out of range {timeout[state_index-1]}")
                                break

                        try:
                            self.sequence_handler_scheduler.cancel(self.sequence_handler_sched_event)
                        except:
                            pass

                        if type(handler) == list:
                            handler_fn = handler[state_index]
                            # schedule handler call if not last
                            if handler_fn and state_index < len(handler)-1:
                                self.run_sequence_handler(handler_fn, timeout[state_index][1]/1000)
                        else:
                            handler_fn = handler

                        state_index += 1
                        state = (state_index, time)
                        if state_index == len(sequence_keys):
                            self.dbg['SEQ'].tr(f"sequence! call handler: {handler_fn}")
                            self.sequences[_key] = (sequence_keys, timeout, (0, 0), handler)
                            handler_fn()
                            return True
                        self.sequences[_key] = (sequence_keys, timeout, state, handler)
                        return False
                except:
                    pass

            # key press does not match any sequence, reset all sequences
            for _key, seq_handler in self.sequences.items():
                self.sequences[_key] = (seq_handler[0], seq_handler[1], (0, 0), seq_handler[3])

        return False

    def process_combos(self, key, time, pressed):
        if len(self.key_pressed) == 0:
            return False

        if pressed:
            for _, combo_handler in self.combos.items():
                combo_keys = combo_handler[0]
                handler = combo_handler[1]
                self.dbg['COMBO'].tr(f"process_combos: {combo_handler}")
                try:
                    if combo_keys[-1] == key:
                        self.dbg['COMBO'].tr(f"process_combos: {combo_keys}")
                        if all([self.key_pressed.get(k, 0) for k in combo_keys[:-1]]):
                            self.dbg['COMBO'].tr(f"combo!")
                            handler()
                            return True
                except:
                    pass
        return False

    def repeat_needed(self, key):
        if self.is_mod_key(key):
            return False
        if key == 'morse':
            return False
        return True

    def key_repeat_sched_fn(self, key):
        self.dbg['REPEAT'].tr(f"key_repeat_sched_fn: {key}")
        if key in self.key_pressed: # may race with key_event, only read dict no lock needed
            keyboard.press(key)
            self.run_repeat(key, self.key_repeat_time)

    def sequence_handle_sched_fn(self, handler):
        self.dbg['SEQ'].tr(f"sequence_handle_sched_fn: {handler}")
        handler()

    def process_workarounds(self, press_keys):
        # workaround for '_', '?', ':'
        if len(press_keys) == 2:
            if press_keys[0].endswith('shift'):
                check_shift_combo = press_keys.copy()
                check_shift_combo[0] = 'shift'

                combine = [ (['shift','-'], '_'), (['shift','/'], '?'), (['shift',';'], ':')]
                for combo in combine:
                    if check_shift_combo == combo[0]:
                        keyboard.press(combo[1])
                        press_keys = []
        return press_keys

    def morse_handle_timeout(self):
        #self.dbg['MORSE'].tr(f"morse_handle_timeout")
        def morse_get_char(tap_stack):
            morse_code = {
                '.-': 'A', '-...': 'B', '-.-.': 'C', '-..': 'D', '.': 'E', '..-.': 'F',
                '--.': 'G', '....': 'H', '..': 'I', '.---': 'J', '-.-': 'K', '.-..': 'L',
                '--': 'M', '-.': 'N', '---': 'O', '.--.': 'P', '--.-': 'Q', '.-.': 'R',
                '...': 'S', '-': 'T', '..-': 'U', '...-': 'V', '.--': 'W', '-..-': 'X',
                '-.--': 'Y', '--..': 'Z',
                '.----': '1', '..---': '2', '...--': '3', '....-': '4', '.....': '5',
                '-....': '6', '--...': '7', '---..': '8', '----.': '9', '-----': '0',
                '...---...': 'SOS',
            }
            morse = ''.join([tap[0] for tap in tap_stack])
            if morse in morse_code:
                return morse_code[morse]
            return ''

        char = None
        if len(self.morse_tap_stack) > 0:
            char = morse_get_char(self.morse_tap_stack)
            self.morse_tap_stack = []
        self.dbg['MORSE'].tr(f"morse: {char}")
        keyboard.write(' ')

    def handle_morse_key(self, key, time, pressed):
        # https://morsecode.world/international/timing.html
        DIT_DURATION    = 150
        DAH_DURATION    = 3*DIT_DURATION
        SPACE_DIT_DAH   = 1*DIT_DURATION
        SPACING_FACTOR  = 1
        SPACE_CHAR      = int(3*DIT_DURATION*SPACING_FACTOR)
        SPACE_WORD      = int(7*DIT_DURATION*SPACING_FACTOR)

        if self.morse_handler_sched_event:
            try:
                self.morse_handler_scheduler.cancel(self.morse_handler_sched_event)
            except:
                pass
            self.morse_handler_sched_event = None

        if pressed:
            if self.morse_beep:
                self.morse_beep.set_volume(-60)
            self.key_pressed[key] = time
        else:
            if self.morse_beep:
                self.morse_beep.set_volume(-200)

            press_duration = self.time_elapsed(self.key_pressed[key], time)
            dit_dah = '-'
            if press_duration < DIT_DURATION:
                dit_dah = '.'

            if len(self.morse_tap_stack) > 0:
                last_tap = self.morse_tap_stack[-1]
                last_tap_release_time = last_tap[2]
            else:
                last_tap_release_time = 0

            space_time_didah = self.time_elapsed(last_tap_release_time, self.key_pressed[key])
            self.dbg['MORSE'].tr(f"morse: {dit_dah} ({space_time_didah}, {press_duration} ms)")
            self.morse_tap_stack.append((dit_dah, self.key_pressed[key], time))
            try:
                keyboard.write(dit_dah)
            except:
                pass

            if key in self.key_pressed:
                del self.key_pressed[key]

            self.run_morse_timeout(SPACE_CHAR/1000)

    def key_event(self, row, col, time, pressed):
        try:
            key = self.key_layout[row][col]
            self.dbg['DEBUG'].tr(f"key_event: {row}, {col}, {time}, {pressed} -> {key}")
        except:
            self.dbg['DEBUG'].tr(f"key_event: {row}, {col}, {time}, {pressed} -> not mapped")
            return

        if key == 'morse':
            self.handle_morse_key(key, time, pressed)
            return

        if pressed:
            press_keys = []
            pressed_mods = self.mod_keys_pressed()
            for mod in pressed_mods:
                self.dbg['DEBUG'].tr(f"mod key: {mod}")
                press_keys.append(mod)
            press_keys.append(key)
            press_keys = self.process_workarounds(press_keys)
            for key in press_keys:
                try:
                    self.dbg['DEBUG'].tr(f"press key: {key}")
                    keyboard.press(key)
                except:
                    pass

        self.process_combos(key, time, pressed)
        self.process_sequences(key, time, pressed)

        if pressed:
            self.key_pressed[key] = time
            self.dbg['DEBUG'].tr(f"key pressed: {self.key_pressed}")
            if len(self.key_pressed) == 1:
                if self.repeat_needed(key):
                    self.dbg['DEBUG'].tr(f"schedule repeat: {key}")
                    self.run_repeat(key, self.key_repeat_delay)
        else:
            if key in self.key_pressed:
                del self.key_pressed[key]
                if len(self.key_pressed) == 0:
                    try:
                        self.key_repeat_scheduler.cancel(self.key_repeat_sched_event)
                        self.key_repeat_sched_event = None
                        self.dbg['DEBUG'].tr(f"schedule repeat canceled: {key}")
                    except:
                        pass
            try:
                keyboard.release(key)
            except:
                pass

        # push on key event stack
        self.key_event_stack.append((((row, col), time, pressed), key))
        if len(self.key_event_stack) > 100:
            self.key_event_stack.pop(0)

    def run_repeat(self, key, time):
        self.dbg['REPEAT'].tr(f"run_repeat: {key}, {time}")
        def run_repeat_schedule_fn(key):
            self.key_repeat_sched_event = self.key_repeat_scheduler.enter(time, 1, self.key_repeat_sched_fn, (key,))
            self.key_repeat_scheduler.run()
        threading.Thread(target=run_repeat_schedule_fn, args=(key,)).start()

    def run_sequence_handler(self, handler, time):
        self.dbg['SEQ'].tr(f"run_sequence_handler: {time}")
        def run_sequence_handle_schedule_fn(handler):
            self.sequence_handler_sched_event = self.sequence_handler_scheduler.enter(time, 1, self.sequence_handle_sched_fn, (handler,))
            self.sequence_handler_scheduler.run()
        threading.Thread(target=run_sequence_handle_schedule_fn, args=(handler,)).start()

    def run_morse_timeout(self, time):
        #self.dbg['MORSE'].tr(f"run_morse_timeout: {time}")
        def run_morse_timeout_schedule_fn():
            self.morse_handler_sched_event = self.morse_handler_scheduler.enter(time, 1, self.morse_handle_timeout)
            self.morse_handler_scheduler.run()
        threading.Thread(target=run_morse_timeout_schedule_fn).start()