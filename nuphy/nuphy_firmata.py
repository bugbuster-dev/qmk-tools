
import sys, traceback
import cv2
import numpy as np

from PySide6 import QtCore
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtWidgets import QTextEdit, QPushButton, QFileDialog, QLabel, QSlider, QLineEdit, QComboBox, QSpacerItem, QSizePolicy
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QSize
from PySide6.QtCore import QRegularExpression
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QImage, QPixmap, QColor, QFont, QTextCursor, QFontMetrics, QMouseEvent, QRegularExpressionValidator, QKeyEvent
import serial
from serial.tools import list_ports

import pyfirmata2
import time

import win32con
import ctypes
import ctypes.wintypes

#-------------------------------------------------------------------------------

firmata_port    = pyfirmata2.Arduino.AUTODETECT
firmata_port    = "COM9"

app_width       = 800
app_height      = 800

#-------------------------------------------------------------------------------

def print_buffer(data):
    # Print 16 byte values per line
    for i, byte in enumerate(data):
        # Print byte value with a space, end parameter prevents new line
        print(f'{byte:02x}', end=' ')
        # After every 16th byte, print a new line
        if (i + 1) % 16 == 0:
            print()  # This causes the line break

    # Handle the case where the data length is not a multiple of 16
    # This ensures we move to a new line after printing the last line, if necessary
    if len(data) % 16 != 0:
        print()  # Ensure there's a newline at the end if the data didn't end on a 16th byte


class Keyboard:
    #---------------------------------------
    FRMT_CMD_RESPONSE   = 0
    FRMT_CMD_SET        = 1
    FRMT_CMD_GET        = 2
    FRMT_CMD_ADD        = 3
    FRMT_CMD_DEL        = 4
    FRMT_CMD_PUB        = 5
    FRMT_CMD_SUB        = 6 # todo subscribe to for example battery status, mcu load, ...

    FRMT_ID_RGB_MATRIX_BUF      = 1
    FRMT_ID_DEFAULT_LAYER       = 2 # todo get default layer
    FRMT_ID_DEBUG_MASK          = 3
    FRMT_ID_BATTERY_STATUS      = 4 # todo 0=charging, 1=discharging, 2=full, 3=not charging, 4=unknown
    FRMT_ID_MACWIN_MODE         = 5

    #---------------------------------------

    RGB_MAXTRIX_W = 19
    RGB_MAXTRIX_H = 6
    MAX_RGB_LED = 110

    DEFAULT_LAYER = 2
    MAX_LAYERS = 8

    def __init__(self):
        pass

    #(0,0)..(18,0)   ->      0..18
    #(0,1)..(18,1)   ->      19..36
    #(0,2)..(18,2)   ->      37..54
    #(0,3)..(18,3)   ->      55..70
    #(0,4)..(18,4)   ->      71..87
    #(0,5)..(18,5)   ->      88..99
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


class FirmataKeyboard(pyfirmata2.Board, QtCore.QObject):
    """
    A keyboard which "talks" firmata.
    """

    signal_console_output = Signal(str)  # signal new console output
    signal_debug_mask = Signal(int)
    signal_macwin_mode = Signal(str)

    MAX_LEN_SYSEX_DATA = 60

    def __init__(self, *args, **kwargs):
        QtCore.QObject.__init__(self)

        self.name = None
        self.port = None
        for arg in kwargs:
            if arg == "name":
                self.name = kwargs[arg]
            if arg == "port":
                self.port = kwargs[arg]

        if self.name == None:
            self.name = self.port

        # pretend its an arduino
        layout = pyfirmata2.BOARDS['arduino']

        self.samplerThread = pyfirmata2.util.Iterator(self)
        self.sp = serial.Serial(self.port, 115200, timeout=1)

        self._layout = layout
        if not self.name:
            self.name = self.port


    def __str__(self):
        return "Keyboard {0.name} on {0.sp.port}".format(self)


    def start(self):
        if self._layout:
            self.setup_layout(self._layout)
        else:
            self.auto_setup()

        self.add_cmd_handler(pyfirmata2.STRING_DATA, self.console_line_handler)
        self.add_cmd_handler(Keyboard.FRMT_CMD_RESPONSE, self.sysex_response_handler)

        self.samplingOn()

        self.send_sysex(pyfirmata2.REPORT_FIRMWARE, [])
        self.send_sysex(pyfirmata2.REPORT_VERSION, [])

        data = bytearray()
        data.append(Keyboard.FRMT_ID_MACWIN_MODE)
        self.send_sysex(Keyboard.FRMT_CMD_GET, data)
        data = bytearray()
        data.append(Keyboard.FRMT_ID_DEBUG_MASK)
        self.send_sysex(Keyboard.FRMT_CMD_GET, data)

        time.sleep(0.5)
        print("-"*80)
        print(f"{self}")
        print(f"firmware:{self.firmware} {self.firmware_version}, firmata={self.get_firmata_version()}")
        print("-"*80)


    def sysex_response_handler(self, *data):
        #print(f"sysex_response_handler: {data}")
        buf = bytearray()
        for i in range(0, len(data), 2):
            # Combine two bytes
            buf.append(data[i+1] << 7 | data[i])
        #print(f"sysex_response_handler: {buf}")
        if buf[0] == Keyboard.FRMT_ID_MACWIN_MODE:
            macwin_mode = chr(buf[1])
            print(f"macwin_mode: {macwin_mode}")
            self.signal_macwin_mode.emit(macwin_mode)
        elif buf[0] == Keyboard.FRMT_ID_DEBUG_MASK:
            dbg_mask = buf[1]
            print(f"debug_mask: {dbg_mask}")
            self.signal_debug_mask.emit(dbg_mask)


    def console_line_handler(self, *data):
        line = pyfirmata2.util.two_byte_iter_to_str(data)
        if line:
            self.signal_console_output.emit(line)  # Emit signal with the received line


    print_pixeldata = 0
    def keyb_rgb_buf_set(self, img, rgb_multiplier):
        #print(rgb_multiplier)
        if self.print_pixeldata:
            print("-"*120)

        height = img.height()
        width = img.width()
        arr = np.ndarray((height, width, 3), buffer=img.constBits(), strides=[img.bytesPerLine(), 3, 1], dtype=np.uint8)

        data = bytearray()
        data.append(Keyboard.FRMT_ID_RGB_MATRIX_BUF)
        for y in range(height):
            for x in range(width):
                pixel = arr[y, x]
                #color = QColor(img.pixelColor(x, y))
                #pixel = (color.red(), color.green(), color.blue())
                rgb_pixel = Keyboard.pixel_to_rgb_index_duration(pixel, Keyboard.xy_to_rgb_index(x, y), 200, rgb_multiplier)
                data.extend(rgb_pixel)

                if self.print_pixeldata:
                    print(f"{x:2},{y:2}=({pixel[0]:3},{pixel[1]:3},{pixel[2]:3})", end=" ")
                    print_buffer(rgb_pixel)

                if len(data) >= self.MAX_LEN_SYSEX_DATA:
                    self.send_sysex(Keyboard.FRMT_CMD_SET, data)
                    data = bytearray()
                    data.append(Keyboard.FRMT_ID_RGB_MATRIX_BUF)

        if len(data) > 0:
            self.send_sysex(Keyboard.FRMT_CMD_SET, data)


    def keyb_default_layer_set(self, layer):
        #print(f"keyb_default_layer_set: {layer}")
        data = bytearray()
        data.append(Keyboard.FRMT_ID_DEFAULT_LAYER)
        data.append(min(layer, 255))
        self.send_sysex(Keyboard.FRMT_CMD_SET, data)


    def keyb_dbg_mask_set(self, dbg_mask):
        #print(f"keyb_dbg_mask_set: {dbg_mask}")
        data = bytearray()
        data.append(Keyboard.FRMT_ID_DEBUG_MASK)
        data.append(min(dbg_mask, 255))
        self.send_sysex(Keyboard.FRMT_CMD_SET, data)

    def keyb_macwin_mode_set(self, macwin_mode):
        print(f"keyb_macwin_mode_set: {macwin_mode}")
        data = bytearray()
        data.append(Keyboard.FRMT_ID_MACWIN_MODE)
        data.append(ord('m') if macwin_mode == 'm' else ord('w'))
        self.send_sysex(Keyboard.FRMT_CMD_SET, data)


    def loop_leds(self, pos):
        if 0:
            data = bytearray()
            data.append(Keyboard.FRMT_ID_RGB_MATRIX_BUF)
            led = Keyboard.xy_to_rgb_index(pos.x, pos.y)
            print(f"x={pos.x}, y={pos.y}, led={led}")
            data.extend([led, 0xff, 0, 0xff, 0xff])

            self.send_sysex(Keyboard.FRMT_CMD_SET, data)

            pos.x = pos.x + 1
            if pos.x >= Keyboard.RGB_MAXTRIX_W:
                pos.x = 0
                pos.y = pos.y + 1
                if pos.y >= Keyboard.RGB_MAXTRIX_H:
                    pos.y = 0

        if 0: # loop through all rgb leds
            data = bytearray()
            data.append(Keyboard.FRMT_ID_RGB_MATRIX_BUF)
            data.extend([pos.i ,0xff,0,0xff,0xff])

            self.send_sysex(Keyboard.FRMT_CMD_SET, data)

            pos.i = (pos.i + 1) % Keyboard.MAX_RGB_LED



class ConsoleTab(QWidget):
    signal_dbg_mask = Signal(int)
    signal_macwin_mode = Signal(str)

    def __init__(self):
        super().__init__()
        self.initUI()

    def update_keyb_dbg_mask(self):
        dbg_mask = int(self.dbgMaskInput.text(),16)
        self.signal_dbg_mask.emit(dbg_mask)

    def update_keyb_macwin_mode(self, event):
        macwin_mode = self.macWinModeSelector.currentText()
        self.signal_macwin_mode.emit(macwin_mode)


    def initUI(self):
        hLayout = QHBoxLayout()
        dbgMaskLabel = QLabel("debug mask")
        metrics = QFontMetrics(dbgMaskLabel.font())
        dbgMaskLabel.setFixedHeight(metrics.height())

        # debug mask hex byte input
        self.dbgMaskInput = QLineEdit()
        # Set a validator to allow only hex characters (0-9, A-F, a-f) and limit to 2 characters
        regExp = QRegularExpression("[0-9A-Fa-f]{1,2}")
        self.dbgMaskInput.setValidator(QRegularExpressionValidator(regExp))

        self.dbgMaskUpdateButton = QPushButton("set")
        self.dbgMaskUpdateButton.clicked.connect(self.update_keyb_dbg_mask)

        hLayout.addWidget(self.dbgMaskUpdateButton)
        hLayout.addWidget(dbgMaskLabel)
        hLayout.addWidget(self.dbgMaskInput)

        macWinLabel = QLabel("mac/win mode")
        self.macWinModeSelector = QComboBox()
        self.macWinModeSelector.addItem('m')
        self.macWinModeSelector.addItem('w')
        hLayout.addWidget(macWinLabel)
        hLayout.addWidget(self.macWinModeSelector)
        self.macWinModeSelector.setCurrentIndex(1)
        self.macWinModeSelector.currentIndexChanged.connect(self.update_keyb_macwin_mode)

        #---------------------------------------
        layout = QVBoxLayout()
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)

        font = QFont()
        font.setFamily("Courier New");
        self.console_output.setFont(font);

        layout.addLayout(hLayout)
        layout.addWidget(self.console_output)
        self.setLayout(layout)


    def update_text(self, text):
        self.console_output.insertPlainText(text)
        self.console_output.ensureCursorVisible()

    def update_debug_mask(self, dbg_mask):
        self.dbgMaskInput.setText(f"{dbg_mask:02x}")

    def update_macwin_mode(self, macwin_mode):
        self.macWinModeSelector.setCurrentIndex(0 if macwin_mode == 'm' else 1)


class RGBMatrixTab(QWidget):
    rgb_frame_signal = Signal(QImage, object)  # Signal to send rgb frame

    def __init__(self):
        super().__init__()
        self.cap = None
        self.frameRate = 25
        self.RGB_multiplier = (1.0,1.0,1.0)
        self.initUI()

    def initUI(self):
        self.layout = QVBoxLayout()
        self.videoLabel = QLabel("")
        self.videoLabel.setFixedSize(app_width, app_height)  # Set this to desired size

        self.openButton = QPushButton("open file")
        self.openButton.clicked.connect(self.openFile)

        controlsLayout = QHBoxLayout()
        self.frameRateLabel = QLabel("frame rate")
        self.framerateSlider = QSlider(Qt.Horizontal)
        self.framerateSlider.setMinimum(1)  # Minimum framerate
        self.framerateSlider.setMaximum(60)  # Maximum framerate
        self.framerateSlider.setValue(self.frameRate)  # Set the default value
        self.framerateSlider.setTickInterval(1)  # Set tick interval
        self.framerateSlider.setTickPosition(QSlider.TicksBelow)
        self.framerateSlider.setToolTip("frame rate")
        self.framerateSlider.valueChanged.connect(self.adjustFramerate)

        rgbMultiplyLayout = QHBoxLayout()
        self.RGB_R_Label = QLabel("r")
        self.RGB_R_Slider = QSlider(QtCore.Qt.Horizontal)
        self.RGB_R_Slider.setMinimum(0)
        self.RGB_R_Slider.setMaximum(300)
        self.RGB_R_Slider.setValue(int(self.RGB_multiplier[0]*100))
        self.RGB_R_Slider.setTickInterval(10)
        self.RGB_R_Slider.setTickPosition(QSlider.TicksBelow)
        self.RGB_R_Slider.setToolTip("red multiplier")
        self.RGB_R_Slider.valueChanged.connect(self.adjustRGBMultiplier)
        self.RGB_G_Label = QLabel("g")
        self.RGB_G_Slider = QSlider(Qt.Horizontal)
        self.RGB_G_Slider.setMinimum(0)
        self.RGB_G_Slider.setMaximum(300)
        self.RGB_G_Slider.setValue(int(self.RGB_multiplier[1]*100))
        self.RGB_G_Slider.setTickInterval(10)
        self.RGB_G_Slider.setTickPosition(QSlider.TicksBelow)
        self.RGB_G_Slider.setToolTip("green multiplier")
        self.RGB_G_Slider.valueChanged.connect(self.adjustRGBMultiplier)
        self.RGB_B_Label = QLabel("b")
        self.RGB_B_Slider = QSlider(Qt.Horizontal)
        self.RGB_B_Slider.setMinimum(0)
        self.RGB_B_Slider.setMaximum(300)
        self.RGB_B_Slider.setValue(int(self.RGB_multiplier[2]*100))
        self.RGB_B_Slider.setTickInterval(10)
        self.RGB_B_Slider.setTickPosition(QSlider.TicksBelow)
        self.RGB_B_Slider.setToolTip("blue multiplier")
        self.RGB_B_Slider.valueChanged.connect(self.adjustRGBMultiplier)

        controlsLayout.addWidget(self.frameRateLabel)
        controlsLayout.addWidget(self.framerateSlider)
        rgbMultiplyLayout.addWidget(self.RGB_R_Label)
        rgbMultiplyLayout.addWidget(self.RGB_R_Slider)
        rgbMultiplyLayout.addWidget(self.RGB_G_Label)
        rgbMultiplyLayout.addWidget(self.RGB_G_Slider)
        rgbMultiplyLayout.addWidget(self.RGB_B_Label)
        rgbMultiplyLayout.addWidget(self.RGB_B_Slider)

        self.layout.addWidget(self.videoLabel)
        self.layout.addWidget(self.openButton)
        self.layout.addLayout(controlsLayout)
        self.layout.addLayout(rgbMultiplyLayout)

        self.setLayout(self.layout)

        self.timer = QTimer()
        self.timer.timeout.connect(self.displayVideoFrame)

    def adjustFramerate(self, value):
        self.frameRate = value
        if self.cap is not None and self.cap.isOpened():
            self.timer.start(1000 / self.frameRate)

    def adjustRGBMultiplier(self, value):
        if self.sender() == self.RGB_R_Slider:
            self.RGB_multiplier = (value/100, self.RGB_multiplier[1], self.RGB_multiplier[2])
        if self.sender() == self.RGB_G_Slider:
            self.RGB_multiplier = (self.RGB_multiplier[0], value/100, self.RGB_multiplier[2])
        if self.sender() == self.RGB_B_Slider:
            self.RGB_multiplier = (self.RGB_multiplier[0], self.RGB_multiplier[1], value/100)
        #print(self.RGB_multiplier)

    def openFile(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "open file", "", "Video Files (*.mp4 *.avi *.mov *.webm)")
        if fileName:
            self.cap = cv2.VideoCapture(fileName)
            fps = self.cap.get(cv2.CAP_PROP_FPS)  # Get the video's frame rate
            self.frameRate = fps if fps > 0 else 25
            self.framerateSlider.setValue(int(self.frameRate))
            self.timer.start(1000 / self.frameRate)

    def displayVideoFrame(self):
        ret, frame = self.cap.read()
        if ret:
            rgbFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            #self.printRGBData(rgbFrame)  # Print RGB data of the frame
            h, w, ch = rgbFrame.shape
            bytesPerLine = ch * w
            convertToQtFormat = QImage(rgbFrame.data, w, h, bytesPerLine, QImage.Format_RGB888)
            p = convertToQtFormat.scaled(app_width, app_height, aspectMode=QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            self.videoLabel.setPixmap(QPixmap.fromImage(p))

            keyb_rgb = p.scaled(Keyboard.RGB_MAXTRIX_W, Keyboard.RGB_MAXTRIX_H)
            #self.videoLabel.setPixmap(QPixmap.fromImage(keyb_rgb))
            self.rgb_frame_signal.emit(keyb_rgb, self.RGB_multiplier)

    def printRGBData(self, frame):
        # Example function to print RGB data of a frame
        # You might want to process or analyze this data instead of printing
        print(frame[0,0])  # Print RGB values of the top-left pixel as an example


class WinFocusListenThread(QThread):
    winfocus_signal = Signal(str)

    def __init__(self):
        super().__init__()

        #-------------------------------------------------------------------------------
        # window focus listener code from:
        # https://gist.github.com/keturn/6695625
        #
        self.user32 = ctypes.windll.user32
        self.ole32 = ctypes.windll.ole32
        self.kernel32 = ctypes.windll.kernel32

        self.WinEventProcType = ctypes.WINFUNCTYPE(
            None,
            ctypes.wintypes.HANDLE,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LONG,
            ctypes.wintypes.LONG,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD
        )

        # The types of events we want to listen for, and the names we'll use for
        # them in the log output. Pick from
        # http://msdn.microsoft.com/en-us/library/windows/desktop/dd318066(v=vs.85).aspx
        self.eventTypes = {
            win32con.EVENT_SYSTEM_FOREGROUND: "Foreground",
        #    win32con.EVENT_OBJECT_FOCUS: "Focus",
        #    win32con.EVENT_OBJECT_SHOW: "Show",
        #    win32con.EVENT_SYSTEM_DIALOGSTART: "Dialog",
        #    win32con.EVENT_SYSTEM_CAPTURESTART: "Capture",
        #    win32con.EVENT_SYSTEM_MINIMIZEEND: "UnMinimize"
        }

        # limited information would be sufficient, but our platform doesn't have it.
        self.processFlag = getattr(win32con, 'PROCESS_QUERY_LIMITED_INFORMATION',
                              win32con.PROCESS_QUERY_INFORMATION)

        self.threadFlag = getattr(win32con, 'THREAD_QUERY_LIMITED_INFORMATION',
                             win32con.THREAD_QUERY_INFORMATION)

        self.lastTime = 0

    def log(self, msg):
        #print(msg)
        self.winfocus_signal.emit(msg)

    def logError(self, msg):
        sys.stdout.write(msg + '\n')

    def getProcessID(self, dwEventThread, hwnd):
        # It's possible to have a window we can get a PID out of when the thread
        # isn't accessible, but it's also possible to get called with no window,
        # so we have two approaches.

        hThread = self.kernel32.OpenThread(self.threadFlag, 0, dwEventThread)

        if hThread:
            try:
                processID = self.kernel32.GetProcessIdOfThread(hThread)
                if not processID:
                    self.logError("Couldn't get process for thread %s: %s" %
                             (hThread, ctypes.WinError()))
            finally:
                self.kernel32.CloseHandle(hThread)
        else:
            errors = ["No thread handle for %s: %s" %
                      (dwEventThread, ctypes.WinError(),)]

            if hwnd:
                processID = ctypes.wintypes.DWORD()
                threadID = user32.GetWindowThreadProcessId(
                    hwnd, ctypes.byref(processID))
                if threadID != dwEventThread:
                    self.logError("Window thread != event thread? %s != %s" %
                             (threadID, dwEventThread))
                if processID:
                    processID = processID.value
                else:
                    errors.append(
                        "GetWindowThreadProcessID(%s) didn't work either: %s" % (
                        hwnd, ctypes.WinError()))
                    processID = None
            else:
                processID = None

            if not processID:
                for err in errors:
                    self.logError(err)

        return processID

    def getProcessFilename(self, processID):
        hProcess = self.kernel32.OpenProcess(self.processFlag, 0, processID)
        if not hProcess:
            self.logError("OpenProcess(%s) failed: %s" % (processID, ctypes.WinError()))
            return None

        try:
            filenameBufferSize = ctypes.wintypes.DWORD(4096)
            filename = ctypes.create_unicode_buffer(filenameBufferSize.value)
            self.kernel32.QueryFullProcessImageNameW(hProcess, 0, ctypes.byref(filename),
                                                ctypes.byref(filenameBufferSize))

            return filename.value
        finally:
            self.kernel32.CloseHandle(hProcess)

    def callback(self, hWinEventHook, event, hwnd, idObject, idChild, dwEventThread,
                 dwmsEventTime):
        length = self.user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, title, length + 1)

        processID = self.getProcessID(dwEventThread, hwnd)

        shortName = '?'
        if processID:
            filename = self.getProcessFilename(processID)
            if filename:
                shortName = '\\'.join(filename.rsplit('\\', 2)[-2:])

        if hwnd:
            hwnd = hex(hwnd)
        elif idObject == win32con.OBJID_CURSOR:
            hwnd = '<Cursor>'

        #self.log(u"%s:%04.2f\t%-10s\t"
            #u"W:%-8s\tP:%-8d\tT:%-8d\t"
            #u"%s\t%s" % (
            #dwmsEventTime, float(dwmsEventTime - self.lastTime)/1000, self.eventTypes.get(event, hex(event)),
            #hwnd, processID or -1, dwEventThread or -1,
            #shortName, title.value))
        self.log(u"P:%-8d\t%s\t%s" % (processID or -1, shortName, title.value))
        self.lastTime = dwmsEventTime

    def setHook(self, WinEventProc, eventType):
        return self.user32.SetWinEventHook(
            eventType,
            eventType,
            0,
            WinEventProc,
            0,
            0,
            win32con.WINEVENT_OUTOFCONTEXT
        )

    def run(self):
        self.ole32.CoInitialize(0)
        WinEventProc = self.WinEventProcType(self.callback)
        self.user32.SetWinEventHook.restype = ctypes.wintypes.HANDLE

        hookIDs = [self.setHook(WinEventProc, et) for et in self.eventTypes.keys()]

        msg = ctypes.wintypes.MSG()
        while self.user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            self.user32.TranslateMessageW(msg)
            self.user32.DispatchMessageW(msg)

        for hookID in hookIDs:
            self.user32.UnhookWinEvent(hookID)
        ole32.CoUninitialize()


class ProgramSelectorComboBox(QComboBox):
    def __init__(self, winfocusText=None):
        self.winfocusText = winfocusText
        super().__init__(None)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self.winfocusText:
                self.clear()
                lines = self.winfocusText.toPlainText().split('\n')
                self.addItems(lines)
                self.addItem("-")
                #print(self.winfocusText.toPlainText())

        # Call the base class implementation to ensure default behavior
        super().mousePressEvent(event)


class WinFocusListenTab(QWidget):
    keyb_layer_set_signal = Signal(int)


    def __init__(self):
        self.defaultLayer = Keyboard.DEFAULT_LAYER
        self.currentLayer = self.defaultLayer

        super().__init__()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)

        #---------------------------------------
        # default layer
        self.defaultLayerLabel = QLabel("default layer")
        metrics = QFontMetrics(self.defaultLayerLabel.font())
        self.defaultLayerLabel.setFixedHeight(metrics.height())

        layout.addWidget(self.defaultLayerLabel)
        # QComboBox for selecting layer
        self.defLayerSelector = QComboBox()
        self.defLayerSelector.addItems([str(i) for i in range(Keyboard.MAX_LAYERS)])
        layout.addWidget(self.defLayerSelector)
        self.defLayerSelector.setCurrentIndex(self.defaultLayer)
        #---------------------------------------

        # Label for instructions
        self.label = QLabel("select default layer above, the foreground application is traced here below.\n"
                            "select program(s) and the layer to use in the dropdown box below.\n"
                            "select '-' to unselect program."
                            )
        layout.addWidget(self.label)

        # for displaying processes which got foreground focus
        self.winfocusTextEdit = QTextEdit()
        self.winfocusTextEdit.setReadOnly(True)
        self.winfocusTextEdit.setMaximumHeight(180)  # Adjust the height
        self.winfocusTextEdit.textChanged.connect(self.limitLines)
        layout.addWidget(self.winfocusTextEdit)

        #---------------------------------------
        self.programSelector = []
        self.layerSelector = []
        for i in range(3):
            self.programSelector.append(ProgramSelectorComboBox(self.winfocusTextEdit))
            self.programSelector[i].addItems(["" for i in range(5)])
            self.programSelector[i].setCurrentIndex(0)
            layout.addWidget(self.programSelector[i])

            self.layerSelector.append(QComboBox())
            self.layerSelector[i].addItems([str(i) for i in range(Keyboard.MAX_LAYERS)])
            self.layerSelector[i].setCurrentIndex(self.defaultLayer)
            layout.addWidget(self.layerSelector[i])

        #---------------------------------------
        self.setLayout(layout)

        # Connect winfocusTextEdit mouse press event
        self.winfocusTextEdit.mousePressEvent = self.selectLine

    def on_winfocus(self, line):
        self.updateWinfocusText(line)
        self.currentFocus = line

        layerSet = False

        # foreground focus window info
        focus_win = line.split("\t")
        #print(focus_win)
        for i, ps in enumerate(self.programSelector):
            compare_win = self.programSelector[i].currentText().split("\t")
            #print(compare_win)
            if focus_win[0].strip() == compare_win[0].strip() and \
               focus_win[1].strip() == compare_win[1].strip():
                layer = int(self.layerSelector[i].currentText())
                self.keyb_layer_set_signal.emit(layer)
                self.currentLayer = layer
                layerSet = True

        if layerSet:
            return

        if self.currentLayer != self.defaultLayer:
            self.keyb_layer_set_signal.emit(self.defaultLayer)
            self.currentLayer = self.defaultLayer

    def updateWinfocusText(self, line):
        self.winfocusTextEdit.append(line)


    def limitLines(self):
        lines = self.winfocusTextEdit.toPlainText().split('\n')
        if len(lines) > 10:
            self.winfocusTextEdit.setPlainText('\n'.join(lines[-10:]))


    def selectLine(self, event):
        pass
        #cursor = self.winfocusTextEdit.textCursor()
        #cursor = self.winfocusTextEdit.cursorForPosition(event.pos())
        #cursor.select(QTextCursor.LineUnderCursor)
        #selectedText = cursor.selectedText()
        #print(selectedText)


from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.animation as animation
import matplotlib.pyplot as plt

def rgba2rgb( rgba, background=(255,255,255) ):
    # rgba iteration: lines, pixels, rgba value
    row, col, ch = rgba.shape

    if ch == 3:
        return rgba

    assert ch == 4, 'RGBA image has 4 channels.'

    rgb = np.zeros( (row, col, 3), dtype='float32' )
    r, g, b, a = rgba[:,:,0], rgba[:,:,1], rgba[:,:,2], rgba[:,:,3]

    a = np.asarray( a, dtype='float32' ) / 255.0

    R, G, B = background

    rgb[:,:,0] = r * a + (1.0 - a) * R
    rgb[:,:,1] = g * a + (1.0 - a) * G
    rgb[:,:,2] = b * a + (1.0 - a) * B

    return np.asarray( rgb, dtype='uint8' )


def add_method_to_class(class_def, method):
    method_definition = method

    # Execute the method definition and retrieve the method from the local scope
    local_scope = {}
    exec(method_definition, globals(), local_scope)
    for method in list(local_scope.values()):
        #print(f"{method.__name__} added to class {class_def.__name__}")
        # Add the method to the class
        setattr(class_def, method.__name__, method)


class CodeTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFont(QFont("Courier New", 9))
        self.load_text_file("animation.pyfunc")

    def load_text_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                content = file.read()
                self.setPlainText(content)
        except Exception as e:
            print(f"Error opening {filepath}: {e}")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Tab:
            # Insert four spaces instead of a tab
            self.insertPlainText("    ")
        else:
            super().keyPressEvent(event)


class RGBAnimationTab(QWidget):
    rgb_frame_signal = Signal(QImage, object)  # Signal to send rgb frame

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        # Create a figure for plotting
        self.figure = Figure(facecolor='black')
        self.figure.subplots_adjust(left=0, right=1, bottom=0, top=1)  # Adjust margins
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('black')
        self.ax.axis('off')

        # start animation button
        self.startButton = QPushButton("start")
        self.startButton.clicked.connect(self.startAnimation)

        # Layout to hold the canvas and buttons
        layout = QVBoxLayout()
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.code_editor = CodeTextEdit()
        #layout.addSpacerItem(spacer)
        layout.addWidget(self.code_editor)
        layout.addWidget(self.canvas)
        layout.addWidget(self.startButton)
        self.setLayout(layout)

        self.figure.set_size_inches((4,3))
        self.figure.set_dpi(100)

        # Parameters for the animation
        self.x_size = 20
        self.frames = 500
        self.interval = 20

        # Animation placeholder
        self.ani = None


    def startAnimation(self):
        if self.ani is None:  # Prevent multiple instances if already running
            add_method_to_class(RGBAnimationTab, self.code_editor.toPlainText())
            try:
                init_fn_name, animate_fn_name = self.animate_methods()
                animate_init_method = getattr(RGBAnimationTab, init_fn_name)
                animate_method = getattr(RGBAnimationTab, animate_fn_name)
                setattr(RGBAnimationTab, "animate_init", animate_init_method)
                setattr(RGBAnimationTab, "animate", animate_method)
                self.animate_init()
                self.ani = animation.FuncAnimation(self.figure, self._animate, frames=self.frames, #init_func=self.init,
                                                blit=True, interval=self.interval, repeat=True)
            except Exception as e:
                print(e)


            if self.ani:
                self.timer = QTimer()
                self.timer.timeout.connect(self.captureAnimationFrame)
                self.timer.start(1000/self.interval)

                self.startButton.setText("stop")
        else:
            self.timer.stop()
            self.ani.event_source.stop()
            self.ani = None

            self.startButton.setText("start")


    print_size = 0
    def captureAnimationFrame(self):
        if self.ani == None:
            return

        self.ani.pause()

        self.canvas.draw()
        buffer = np.frombuffer(self.canvas.buffer_rgba(), dtype=np.uint8)
        width, height = self.figure.get_size_inches() * self.figure.get_dpi()
        if self.print_size:
            print(f"canvas size: {width}x{height}")
            self.print_size = 0
        img = buffer.reshape(int(height), int(width), 4)
        img = rgba2rgb(img)
        qimage = QImage(img.data, width, height, QImage.Format_RGB888)
        keyb_rgb = qimage.scaled(Keyboard.RGB_MAXTRIX_W, Keyboard.RGB_MAXTRIX_H)
        self.rgb_frame_signal.emit(keyb_rgb, (10.0,10.0,10.0))

        self.ani.resume()

    def _animate(self, i):
        ret = self.animate(i)
        if i == self.frames:
            self.figure.clear()
        return ret

    def init_wave(self):
        # Line object for the standing wave
        self.standing_wave_line, = self.ax.plot([], [], color='cyan', lw=50)
        self.standing_wave_line.set_data([], [])
        return self.standing_wave_line,


    def animate_wave(self, i):
        x = np.linspace(0, self.x_size, 1000)
        #x = np.linspace(0, 2 * np.pi, 1000)

        amplitude = np.sin(np.pi * i / self.frames) * 1
        y = amplitude * np.sin(2 * 2 * np.pi * 2 * (x - self.x_size / 2) / self.x_size) * np.cos(2 * np.pi * i / 50)
        self.standing_wave_line.set_data((x - self.x_size / 2)/100, y/30)

        return self.standing_wave_line,


    def init_rect(self):
        self.frames = 1000
        self.rect = plt.Rectangle((0.5, 0.5), 0.15, 0.3, color="blue")
        self.ax.add_patch(self.rect)
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(0, 1)

        # Initialize velocity and direction
        self.velocity = np.array([0.01, 0.007])

        # Set the initial state of the rectangle, if needed
        self.rect.set_xy((0.45, 0.45))
        return self.rect,

    def animate_rect(self, i):
        pos = self.rect.get_xy()
        pos += self.velocity

        # Check for collision with the walls and reverse velocity if needed
        if pos[0] <= 0 or pos[0] + self.rect.get_width() >= 1:
            self.velocity[0] = -self.velocity[0]
        if pos[1] <= 0 or pos[1] + self.rect.get_height() >= 1:
            self.velocity[1] = -self.velocity[1]

        self.rect.set_xy(pos)
        return self.rect,


#-------------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('QMK Firmata')
        self.setGeometry(100, 100, app_width, app_height)
        self.setFixedSize(app_width, app_height)

        #-----------------------------------------------------------
        # add tabs
        tab_widget = QTabWidget()
        self.console_tab = ConsoleTab()
        self.rgb_matrix_tab = RGBMatrixTab()
        self.rgb_animation_tab = RGBAnimationTab()
        self.winfocus_tab = WinFocusListenTab()

        tab_widget.addTab(self.console_tab, 'console')
        tab_widget.addTab(self.rgb_matrix_tab, 'rgb video')
        tab_widget.addTab(self.rgb_animation_tab, 'rgb animation')
        tab_widget.addTab(self.winfocus_tab, 'layer auto switch')


        self.setCentralWidget(tab_widget)
        #-----------------------------------------------------------

        # instantiate firmata keyboard
        self.keyboard = FirmataKeyboard(port=firmata_port)
        self.keyboard.signal_console_output.connect(self.console_tab.update_text)
        self.keyboard.signal_debug_mask.connect(self.console_tab.update_debug_mask)
        self.keyboard.signal_macwin_mode.connect(self.console_tab.update_macwin_mode)

        self.winfocus_listen_thread = WinFocusListenThread()
        self.winfocus_listen_thread.winfocus_signal.connect(self.winfocus_tab.on_winfocus)
        self.winfocus_listen_thread.start()

        self.console_tab.signal_dbg_mask.connect(self.keyboard.keyb_dbg_mask_set)
        self.console_tab.signal_macwin_mode.connect(self.keyboard.keyb_macwin_mode_set)
        self.rgb_matrix_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.rgb_animation_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.winfocus_tab.keyb_layer_set_signal.connect(self.keyboard.keyb_default_layer_set)

        self.keyboard.start()


def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())

def list_com_ports(vid = None, pid = None):
    device_list = list_ports.comports()
    for device in device_list:
        print(f"{device}: vid={device.vid:04X}, pid={device.pid:04X}")
        if device.vid == vid and (pid == None or device.pid == pid):
            port = device.device

#-------------------------------------------------------------------------------

if __name__ == "__main__":
    #list_com_ports()
    main()
