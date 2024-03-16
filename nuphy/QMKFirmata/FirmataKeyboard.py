
import pyfirmata2

from PySide6 import QtCore
from PySide6.QtCore import Qt, QThread, Signal, QTimer
import numpy as np

import serial
from serial.tools import list_ports
import time

from DebugTracer import DebugTracer

import glob
import importlib.util
import inspect
import os
from pathlib import Path


#-------------------------------------------------------------------------------

#region list com ports
def list_com_ports(vid = None, pid = None):
    device_list = list_ports.comports()
    for device in device_list:
        print(f"{device}: vid={device.vid:04x}, pid={device.pid:04x}")

def find_com_port(vid, pid):
    device_list = list_ports.comports()
    for device in device_list:
        #print(f"{device}: vid={device.vid:04x}, pid={device.pid:04x}")
        if device.vid == vid and (pid == None or device.pid == pid):
            return device.device
    return None
#endregion

#-------------------------------------------------------------------------------

class DefaultKeyboardModel:
    #---------------------------------------
    RGB_MAXTRIX_W = 19
    RGB_MAXTRIX_H = 6
    NUM_RGB_LEDS = 110

    DEFAULT_LAYER = 2
    NUM_LAYERS = 8

    def __init__(self, name):
        self.name = name
        pass

    def xy_to_rgb_index(x, y):
        return y * DefaultKeyboardModel.RGB_MAXTRIX_W + x


class FirmataKeybCmd:
    RESPONSE   = 0 # response to a command
    SET        = 1 # set a value for 'ID_...'
    GET        = 2 # get a value for 'ID_...'
    ADD        = 3 # add a value to 'ID_...'
    DEL        = 4 # delete a value from 'ID_...'
    PUB        = 5 # todo needed? can put it in 'RESPONSE'
    SUB        = 6 # todo subscribe to for example battery status, mcu load, ...

    ID_RGB_MATRIX_BUF      = 1
    ID_DEFAULT_LAYER       = 2 # todo get default layer
    ID_DEBUG_MASK          = 3
    ID_BATTERY_STATUS      = 4
    ID_MACWIN_MODE         = 5

class FirmataKeyboard(pyfirmata2.Board, QtCore.QObject):
    """
    A keyboard which "talks" firmata.
    """
    #-------------------------------------------------------------------------------
    signal_console_output = Signal(str)  # signal new console output
    signal_debug_mask = Signal(int)
    signal_macwin_mode = Signal(str)
    #-------------------------------------------------------------------------------

    MAX_LEN_SYSEX_DATA = 60

    @staticmethod
    def pixel_to_rgb_index_duration(pixel, index, duration, brightness=(1.0,1.0,1.0)):
        data = bytearray()
        #print(brightness)
        data.append(index)
        data.append(duration)
        data.append(min(int(pixel[0]*brightness[0]), 255))
        data.append(min(int(pixel[1]*brightness[1]), 255))
        data.append(min(int(pixel[2]*brightness[2]), 255))
        return data

    @staticmethod
    def loadKeyboardModels(path="keyboards"):
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


    def __init__(self, *args, **kwargs):
        QtCore.QObject.__init__(self)
        #----------------------------------------------------
        #region debug tracers
        self.dbg = {}
        self.dbg['DEBUG']           = DebugTracer(print=1, trace=1)
        self.dbg['SYSEX_COMMAND']   = DebugTracer(print=0, trace=1)
        self.dbg['SYSEX_RESPONSE']  = DebugTracer(print=0, trace=1)
        self.dbg['RGB_BUF']         = DebugTracer(print=0, trace=1)
        dbg = self.dbg['DEBUG']
        #endregion
        #----------------------------------------------------
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

        # load "keyboard models", keyboard model contains name, vid/pid, rgb matrix size, ...
        self.keyboardModel, self.keyboardModelVidPid = self.loadKeyboardModels()
        if dbg.print:
            for class_name, class_type in self.keyboardModel.items():
                dbg.tr(f"keyboard model: {class_name} ({hex(class_type.vid_pid()[0])}:{hex(class_type.vid_pid()[1])}), {class_type}")
            #for vid_pid, class_type in self.keyboardModelVidPid.items():
                #dbg.tr(f"vid pid: {vid_pid}, Class Type: {class_type}")

        if self.port == None and self.vid_pid:
            self.port = find_com_port(self.vid_pid[0], self.vid_pid[1])
            self.keyboardModel = self.keyboardModelVidPid[(self.vid_pid[0], self.vid_pid[1])]
            dbg.tr(f"using keyboard: {self.keyboardModel}")
            self.name = self.keyboardModel.name()

        self.samplerThread = pyfirmata2.util.Iterator(self)
        self.sp = serial.Serial(self.port, 115200, timeout=1)

        # pretend its an arduino
        self._layout = pyfirmata2.BOARDS['arduino']
        if not self.name:
            self.name = self.port


    def __str__(self):
        return "Keyboard {0.name} on {0.sp.port}".format(self)

    def rgb_matrix_size(self):
        if self.keyboardModel:
            return self.keyboardModel.rgb_matrix_size()
        return DefaultKeyboardModel.RGB_MAXTRIX_W, DefaultKeyboardModel.RGB_MAXTRIX_H

    def num_layers(self):
        if self.keyboardModel:
            return self.keyboardModel.num_layers()
        return DefaultKeyboardModel.NUM_LAYERS

    def num_rgb_leds(self):
        if self.keyboardModel:
            return self.keyboardModel.num_rgb_leds()
        return DefaultKeyboardModel.NUM_RGB_LEDS

    def xy_to_rgb_index(self, x, y):
        xy_to_rgb_index =  DefaultKeyboardModel.xy_to_rgb_index
        if self.keyboardModel:
            xy_to_rgb_index = self.keyboardModel.xy_to_rgb_index
        return xy_to_rgb_index(x, y)


    def start(self):
        if self._layout:
            self.setup_layout(self._layout)
        else:
            self.auto_setup()

        self.add_cmd_handler(pyfirmata2.STRING_DATA, self.console_line_handler)
        self.add_cmd_handler(FirmataKeybCmd.RESPONSE, self.sysex_response_handler)

        self.samplingOn()

        self.send_sysex(pyfirmata2.REPORT_FIRMWARE, [])
        self.send_sysex(pyfirmata2.REPORT_VERSION, [])

        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_MACWIN_MODE])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_DEBUG_MASK])
        self.send_sysex(FirmataKeybCmd.GET, [FirmataKeybCmd.ID_BATTERY_STATUS])

        time.sleep(0.5)
        print("-"*80)
        print(f"{self}")
        print(f"firmware:{self.firmware} {self.firmware_version}, firmata={self.get_firmata_version()}")
        print("-"*80)


    def stop(self):
        self.samplingOff()
        try:
            self.sp.close()
        except:
            pass

    def sysex_response_handler(self, *data):
        dbg = self.dbg['SYSEX_RESPONSE']
        #dbg.tr(f"sysex_response_handler: {data}")

        buf = bytearray()
        if len(data) % 2 != 0:
            dbg.tr(f"sysex_response_handler: invalid data length {len(data)}")
            return

        for i in range(0, len(data), 2):
            # Combine two bytes
            buf.append(data[i+1] << 7 | data[i])

        if dbg.print:
            dbg.tr("-"*40)
            dbg.tr(f"sysex response:\n{buf.hex(' ')}")

        if buf[0] == FirmataKeybCmd.ID_MACWIN_MODE:
            macwin_mode = chr(buf[1])
            dbg.tr(f"macwin mode: {macwin_mode}")
            self.signal_macwin_mode.emit(macwin_mode)
        elif buf[0] == FirmataKeybCmd.ID_DEBUG_MASK:
            dbg_mask = buf[1]
            dbg.tr(f"debug mask: {dbg_mask}")
            self.signal_debug_mask.emit(dbg_mask)
        elif buf[0] == FirmataKeybCmd.ID_BATTERY_STATUS:
            battery_charging = buf[1]
            battery_level = buf[2]
            dbg.tr(f"battery charging: {battery_charging}, battery level: {battery_level}")
            #self.signal_battery_status.emit(battery_charging, battery_level)


    def console_line_handler(self, *data):
        line = pyfirmata2.util.two_byte_iter_to_str(data)
        if line:
            self.signal_console_output.emit(line)  # Emit signal with the received line


    def keyb_rgb_buf_set(self, img, rgb_multiplier):
        dbg = self.dbg['RGB_BUF']
        if dbg.print:
            dbg.tr("-"*120)
            dbg.tr(f"rgb mult {rgb_multiplier}")

        height = img.height()
        width = img.width()
        arr = np.ndarray((height, width, 3), buffer=img.constBits(), strides=[img.bytesPerLine(), 3, 1], dtype=np.uint8)

        data = bytearray()
        data.append(FirmataKeybCmd.ID_RGB_MATRIX_BUF)
        for y in range(height):
            for x in range(width):
                pixel = arr[y, x]
                #color = QColor(img.pixelColor(x, y))
                #pixel = (color.red(), color.green(), color.blue())

                rgb_pixel = self.pixel_to_rgb_index_duration(pixel, self.xy_to_rgb_index(x, y), 200, rgb_multiplier)
                data.extend(rgb_pixel)

                if dbg.print:
                    dbg.tr(f"{x:2},{y:2}=({pixel[0]:3},{pixel[1]:3},{pixel[2]:3})", end=" ")
                    dbg.tr(rgb_pixel.hex(' '))

                if len(data) >= self.MAX_LEN_SYSEX_DATA:
                    self.send_sysex(FirmataKeybCmd.SET, data)
                    data = bytearray()
                    data.append(FirmataKeybCmd.ID_RGB_MATRIX_BUF)

        if len(data) > 0:
            self.send_sysex(FirmataKeybCmd.SET, data)


    def keyb_default_layer_set(self, layer):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_default_layer_set: {layer}")

        data = bytearray()
        data.append(FirmataKeybCmd.ID_DEFAULT_LAYER)
        data.append(min(layer, 255))
        self.send_sysex(FirmataKeybCmd.SET, data)


    def keyb_dbg_mask_set(self, dbg_mask):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_dbg_mask_set: {dbg_mask}")

        data = bytearray()
        data.append(FirmataKeybCmd.ID_DEBUG_MASK)
        data.append(min(dbg_mask, 255))
        self.send_sysex(FirmataKeybCmd.SET, data)

    def keyb_macwin_mode_set(self, macwin_mode):
        dbg = self.dbg['SYSEX_COMMAND']
        dbg.tr(f"keyb_macwin_mode_set: {macwin_mode}")

        data = bytearray()
        data.append(FirmataKeybCmd.ID_MACWIN_MODE)
        data.append(ord(macwin_mode))
        self.send_sysex(FirmataKeybCmd.SET, data)


    def loop_leds(self, pos):
        if 0:
            data = bytearray()
            data.append(FirmataKeybCmd.ID_RGB_MATRIX_BUF)
            led = self.xy_to_rgb_index(pos.x, pos.y)
            print(f"x={pos.x}, y={pos.y}, led={led}")
            data.extend([led, 0xff, 0, 0xff, 0xff])

            self.send_sysex(FirmataKeybCmd.SET, data)

            pos.x = pos.x + 1
            if pos.x >= self.rgb_matrix_size()[0]:
                pos.x = 0
                pos.y = pos.y + 1
                if pos.y >= self.rgb_matrix_size()[1]:
                    pos.y = 0

        if 0: # loop through all rgb leds
            data = bytearray()
            data.append(FirmataKeybCmd.ID_RGB_MATRIX_BUF)
            data.extend([pos.i ,0xff,0,0xff,0xff])

            self.send_sysex(FirmataKeybCmd.SET, data)

            pos.i = (pos.i + 1) % self.num_rgb_leds()

