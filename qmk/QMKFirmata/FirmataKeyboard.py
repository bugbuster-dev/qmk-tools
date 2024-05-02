from PySide6 import QtCore
from PySide6.QtCore import Signal
from PySide6.QtGui import QImage, QColor, QPainter

import pyfirmata2, hid, serial, time, numpy as np
import glob, inspect, os, importlib.util, struct
from pathlib import Path

from DebugTracer import DebugTracer

#todo: add license
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

    def _reconfigure_port(self):
        pass

    def _read_msg(self):
        try:
            data = bytearray(self.hid_device.read(self.epsize, self.timeout))
            #self.dbg.tr(f"rawhid read:{data.hex(' ')}")
            data = data.rstrip(bytearray([0])) # remove trailing zeros
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
    ID_CONFIG_LAYOUT        = 8
    ID_CONFIG               = 9
    ID_CONFIG_EXTENDED      = 0
    ID_CONFIG_DEBUG         = 1
    ID_CONFIG_DEBUG_USER    = 2
    ID_CONFIG_RGB           = 3
    ID_CONFIG_KEYMAP        = 4

# todo: dictionary with version as key
FirmataKeybCmd = FirmataKeybCmd_v0_2

class FirmataKeyboard(pyfirmata2.Board, QtCore.QObject):
    """
    A keyboard which "talks" arduino firmata.
    """
    #-------------------------------------------------------------------------------
    # signal received qmk keyboard data
    signal_console_output = Signal(str)
    signal_debug_mask = Signal(int, int)
    signal_macwin_mode = Signal(str)
    signal_default_layer = Signal(int)
    signal_rgb_matrix_mode = Signal(int)
    signal_rgb_matrix_hsv = Signal(tuple)
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

    def __init__(self, *args, **kwargs):
        QtCore.QObject.__init__(self)
        #----------------------------------------------------
        #region debug tracers
        self.dbg_rgb_buf = 0
        self.dbg = {}
        self.dbg['ERROR']           = DebugTracer(print=1, trace=1, obj=self)
        self.dbg['DEBUG']           = DebugTracer(print=1, trace=1, obj=self)
        self.dbg['SYSEX_COMMAND']   = DebugTracer(print=1, trace=1, obj=self)
        self.dbg['SYSEX_RESPONSE']  = DebugTracer(print=1, trace=1, obj=self)
        self.dbg['RGB_BUF']         = DebugTracer(print=0, trace=1, obj=self)
        dbg = self.dbg['DEBUG']
        #endregion
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

        self.config_layout = {}
        self.config_model = None
        self.add_cmd_handler(pyfirmata2.STRING_DATA, self.console_line_handler)
        self.add_cmd_handler(FirmataKeybCmd.RESPONSE, self.sysex_response_handler)

        self.samplingOn()
        self.send_sysex(pyfirmata2.REPORT_FIRMWARE, [])
        self.send_sysex(pyfirmata2.REPORT_VERSION, [])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG_LAYOUT])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_MACWIN_MODE])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_DEBUG_MASK])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_BATTERY_STATUS])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_RGB_MATRIX_MODE])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_RGB_MATRIX_HSV])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG, FirmataKeybCmd.ID_CONFIG_DEBUG])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG, FirmataKeybCmd.ID_CONFIG_DEBUG_USER])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG, FirmataKeybCmd.ID_CONFIG_RGB])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_CONFIG, FirmataKeybCmd.ID_CONFIG_KEYMAP])

        time.sleep(1)
        print("-"*80)
        print(f"{self}")
        print(f"qmk firmata version:{self.firmware} {self.firmware_version}, firmata={self.get_firmata_version()}")
        print("-"*80)

        self.signal_config_model.emit(self.config_model)

    def stop(self):
        try:
            self.sp.close()
        except Exception as e:
            self.dbg['ERROR'].tr(f"{e}")
        self.samplingOff()

    #-------------------------------------------------------------------------------
    def sysex_response_handler(self, *data):
        dbg = self.dbg['SYSEX_RESPONSE']
        #dbg.tr(f"sysex_response_handler: {data}")
        buf = bytearray()
        if len(data) % 2 != 0:
            self.dbg['ERROR'].tr(f"sysex_response_handler: invalid data length {len(data)}")
            return

        for off in range(0, len(data), 2):
            # Combine two bytes
            buf.append(data[off+1] << 7 | data[off])

        if dbg.print:
            dbg.tr("-"*40)
            dbg.tr(f"sysex response:\n{buf.hex(' ')}")

        if buf[0] == FirmataKeybCmd.ID_MACWIN_MODE:
            macwin_mode = chr(buf[1])
            dbg.tr(f"macwin mode: {macwin_mode}")
            self.signal_macwin_mode.emit(macwin_mode)
            self.signal_default_layer.emit(self.default_layer(macwin_mode))
        elif buf[0] == FirmataKeybCmd.ID_DEBUG_MASK:
            dbg_mask = 0
            dbg_user_mask = 0
            try:
                dbg_mask = struct.unpack_from('<I', buf, 1)[0]
                dbg_user_mask = struct.unpack_from('<I', buf, 5)[0]
            except Exception as e:
                self.dbg['ERROR'].tr(f"sysex_response_handler:ID_DEBUG_MASK:{e}")
            dbg.tr(f"debug mask: {hex(dbg_mask)} {hex(dbg_user_mask)}")
            self.signal_debug_mask.emit(dbg_mask, dbg_user_mask)
        elif buf[0] == FirmataKeybCmd.ID_BATTERY_STATUS:
            battery_charging = buf[1]
            battery_level = buf[2]
            dbg.tr(f"battery charging: {battery_charging}, battery level: {battery_level}")
        elif buf[0] == FirmataKeybCmd.ID_RGB_MATRIX_MODE:
            matrix_mode = buf[1]
            dbg.tr(f"rgb matrix mode: {matrix_mode}")
            self.signal_rgb_matrix_mode.emit(matrix_mode)
        elif buf[0] == FirmataKeybCmd.ID_RGB_MATRIX_HSV:
            h = buf[1]; s = buf[2]; v = buf[3]
            dbg.tr(f"rgb matrix hsv: {h}, {s}, {v}")
            self.signal_rgb_matrix_hsv.emit((h,s,v))
        elif buf[0] == FirmataKeybCmd.ID_CONFIG_LAYOUT:
            off = 1
            config_id = buf[off]; off += 1
            config_size = buf[off]; off += 1
            dbg.tr(f"config id: {config_id}, size: {config_size}")
            config_fields = {}
            config_field = buf[off]
            while config_field != 0:
                field_type = buf[off+1]
                field_offset = buf[off+2]
                field_size = buf[off+3]
                config_fields[config_field] = (field_type, field_offset, field_size)
                off += 4
                try:
                    config_field = buf[off]
                except:
                    break
            # config layout used to get/set of config field values in byte buffer
            self.config_layout[config_id] = config_fields
            self.keyboardModel.keyb_config().print_config_layout(config_id, config_fields)
            self.config_model = self.keyboardModel.keyb_config().keyb_config_model(self.config_model, config_id, config_fields)
        elif buf[0] == FirmataKeybCmd.ID_CONFIG:
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
                elif field_type == TYPE_ARRAY:
                    value = buf[off:off+field_size]
                else:
                    value = 0
                field_values[field_id] = value
                dbg.tr(f"config[{config_id}][{field_id}]: {value}")
                if off >= len(buf):
                    break
            # signal to gui the config values
            self.signal_config.emit((config_id, field_values))

    def console_line_handler(self, *data):
        line = pyfirmata2.util.two_byte_iter_to_str(data)
        #self.dbg['DEBUG'].tr(f"console: {line}")
        if line:
            self.signal_console_output.emit(line)

    #-------------------------------------------------------------------------------
    def keyb_set_rgb_buf(self, img, rgb_multiplier):
        if self.dbg_rgb_buf:
            self.dbg['RGB_BUF'].tr("-"*120)
            self.dbg['RGB_BUF'].tr(f"rgb mult {rgb_multiplier}")

        #self.dbg['DEBUG'].tr(f"rgb img from sender {self.sender()} {img}")
        if not img:
            self.dbg['DEBUG'].tr(f"sender {self.sender()} stopped")
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

    def keyb_set_dbg_mask(self, dbg_mask, dbg_user_mask):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_dbg_mask: {dbg_mask}")
        data = bytearray()
        data.append(FirmataKeybCmd.ID_DEBUG_MASK)
        data.extend(bytearray(struct.pack('<I', dbg_mask)))
        data.extend(bytearray(struct.pack('<I', dbg_user_mask)))
        self.send_sysex(FirmataKeybCmd.SET, data)

    def keyb_set_macwin_mode(self, macwin_mode):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_macwin_mode: {macwin_mode}")
        data = bytearray()
        data.append(FirmataKeybCmd.ID_MACWIN_MODE)
        data.append(ord(macwin_mode))
        self.send_sysex(FirmataKeybCmd.SET, data)

    def keyb_set_rgb_matrix_mode(self, mode):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_rgb_matrix_mode: {mode}")
        data = bytearray()
        data.append(FirmataKeybCmd.ID_RGB_MATRIX_MODE)
        data.append(mode)
        self.send_sysex(FirmataKeybCmd.SET, data)

    def keyb_set_rgb_matrix_hsv(self, hsv):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_set_rgb_matrix_hsv: {hsv}")
        data = bytearray()
        data.append(FirmataKeybCmd.ID_RGB_MATRIX_HSV)
        data.append(hsv[0])
        data.append(hsv[1])
        data.append(hsv[2])
        self.send_sysex(FirmataKeybCmd.SET, data)

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
                elif field_type == TYPE_UINT64: # todo: remove uint64/float/array
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
