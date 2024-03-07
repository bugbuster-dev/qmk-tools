
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
from PySide6.QtGui import QImage, QPixmap, QColor, QFont, QTextCursor, QFontMetrics, QMouseEvent, QRegularExpressionValidator
import serial
from serial.tools import list_ports

import pyfirmata2
import time

import win32con
import ctypes
import ctypes.wintypes

#-------------------------------------------------------------------------------

port        = pyfirmata2.Arduino.AUTODETECT
port        = "COM9"

width       = 800
height      = 600

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
    SYSEX_RGB_MATRIX_CMD = 0x01
    SYSEX_DEFAULT_LAYER_SET = 0x02
    SYSEX_DEBUG_MASK_SET = 0x03
    
    RGB_MAXTRIX_W = 19
    RGB_MAXTRIX_H = 6

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
            if x >= 4 and x <= 9:
                x = 4
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
    
    
class KeybFirmataThread(QThread):
    console_signal = Signal(str)  # Signal to send data to the main thread
    
    MAX_LEN_SYSEX_DATA = 60

    def __init__(self, port):
        self.port   = port
        self.board  = None
        super().__init__()

    def console_line_handler(self, *data):
        line = pyfirmata2.util.two_byte_iter_to_str(data)
        if line:
            self.console_signal.emit(line)  # Emit signal with the received line


    print_pixeldata = 0
    def update_rgb(self, img, rgb_multiplier):
        if self.board == None:
            return

        #print(rgb_multiplier)
        if self.print_pixeldata:
            print("-"*120)

        height = img.height()
        width = img.width()
        arr = np.ndarray((height, width, 3), buffer=img.constBits(), strides=[img.bytesPerLine(), 3, 1], dtype=np.uint8)

        data = bytearray()
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
                    self.board.send_sysex(Keyboard.SYSEX_RGB_MATRIX_CMD, data)
                    data = bytearray()
        
        if len(data) > 0:
            self.board.send_sysex(Keyboard.SYSEX_RGB_MATRIX_CMD, data)


    def keyb_default_layer_set(self, layer):
        if self.board == None:
            return
        #print(f"keyb_default_layer_set: {layer}")
        data = bytearray()
        data.append(min(layer, 255))
        self.board.send_sysex(Keyboard.SYSEX_DEFAULT_LAYER_SET, data)


    def dbg_mask_set(self, dbg_mask):
        if self.board == None:
            return
        #print(f"dbg_mask_set: {dbg_mask}")
        data = bytearray()
        data.append(min(dbg_mask, 255))
        self.board.send_sysex(Keyboard.SYSEX_DEBUG_MASK_SET, data)


    def run(self):
        self.board = pyfirmata2.Arduino(self.port)
        self.board.auto_setup()
        
        it = pyfirmata2.util.Iterator(self.board)
        it.start()

        self.board.add_cmd_handler(pyfirmata2.STRING_DATA, self.console_line_handler)

        method_list = [func for func in dir(self.board) if callable(getattr(self.board, func)) and not func.startswith("__")]
        data_list = [func for func in dir(self.board) if not callable(getattr(self.board, func))]
        print("-"*80)
        print(f"{self.board}")
        print("-"*40)
        print(f"{method_list}")
        print("-"*40)
        print(f"{data_list}")
        print("-"*40)
        print(f"firmware:{self.board.firmware} {self.board.firmware_version}, firmata={self.board.firmata_version}")
        print("-"*80)

        #data = bytearray()
        #data.extend([99,0xff,0xff,0,0])
        #self.board.send_sysex(Keyboard.SYSEX_RGB_MATRIX_CMD, data)
        while True:
            time.sleep(0.1)


class ConsoleTab(QWidget):
    dbg_mask_signal = Signal(int)

    def __init__(self):
        super().__init__()
        self.initUI()

    def updateDbgMask(self):
        dbg_mask = int(self.dbgMaskInput.text(),16)
        self.dbg_mask_signal.emit(dbg_mask)
    
    def initUI(self):
        dbgMaskLayout = QHBoxLayout()
        self.dbgMaskLabel = QLabel("debug mask")
        metrics = QFontMetrics(self.dbgMaskLabel.font())
        self.dbgMaskLabel.setFixedHeight(metrics.height())
        
        # debug mask hex byte input
        self.dbgMaskInput = QLineEdit()
        # Set a validator to allow only hex characters (0-9, A-F, a-f) and limit to 2 characters
        regExp = QRegularExpression("[0-9A-Fa-f]{1,2}")
        self.dbgMaskInput.setValidator(QRegularExpressionValidator(regExp))
       
        self.dbgMaskUpdateButton = QPushButton("set")
        self.dbgMaskUpdateButton.clicked.connect(self.updateDbgMask)
        
        dbgMaskLayout.addWidget(self.dbgMaskLabel)
        dbgMaskLayout.addWidget(self.dbgMaskInput)
        dbgMaskLayout.addWidget(self.dbgMaskUpdateButton)
        
        layout = QVBoxLayout()
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)

        font = QFont()
        font.setFamily("Courier New");
        self.console_output.setFont(font);

        layout.addLayout(dbgMaskLayout)
        layout.addWidget(self.console_output)
        self.setLayout(layout)


    def update_text(self, text):
        self.console_output.insertPlainText(text)
        self.console_output.ensureCursorVisible()


class VideoPlayerTab(QWidget):
    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.videoWidget = QVideoWidget()

        self.openButton = QPushButton("Open Video")
        self.openButton.clicked.connect(self.openFile)

        layout.addWidget(self.videoWidget)
        layout.addWidget(self.openButton)

        self.setLayout(layout)
        self.player.setVideoOutput(self.videoWidget)

    def openFile(self):
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Video")
        if fileName != '':
            self.player.setSource(QUrl.fromLocalFile(fileName))
            self.player.play()


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
        self.videoLabel.setFixedSize(width, height)  # Set this to desired size

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
            p = convertToQtFormat.scaled(width, height, aspectMode=QtCore.Qt.AspectRatioMode.KeepAspectRatio)
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
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.animation as animation


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
        layout.addSpacerItem(spacer)
        layout.addWidget(self.canvas)
        layout.addWidget(self.startButton)
        self.setLayout(layout)

        self.figure.set_size_inches((4,3))
        self.figure.set_dpi(100)

        # Parameters for the animation
        self.x_size = 20
        self.frames = 200
        self.interval = 20

        # Line object for the standing wave
        self.standing_wave_line, = self.ax.plot([], [], color='cyan', lw=50)
        
        # Animation placeholder
        self.ani = None


    def startAnimation(self):
        if self.ani is None:  # Prevent multiple instances if already running
            self.ani = animation.FuncAnimation(self.figure, self.animate, frames=self.frames, init_func=self.init, blit=True, interval=self.interval, repeat=True)
            self.canvas.draw()
            
            self.timer = QTimer()
            self.timer.timeout.connect(self.captureAnimationFrame)
            self.timer.start(1000/self.interval)

            self.startButton.setText("stop")
        else:
            self.timer.stop()
            self.ani.event_source.stop()
            self.ani = None
            
            self.startButton.setText("start")


    def init(self):
        self.standing_wave_line.set_data([], [])
        return self.standing_wave_line,


    print_size = 1
    def captureAnimationFrame(self):
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

    def animate(self, i):
        x = np.linspace(0, self.x_size, 1000)
        #x = np.linspace(0, 2 * np.pi, 1000)

        amplitude = np.sin(np.pi * i / self.frames) * 1
        y = amplitude * np.sin(2 * 2 * np.pi * 2 * (x - self.x_size / 2) / self.x_size) * np.cos(2 * np.pi * i / 50)
        self.standing_wave_line.set_data((x - self.x_size / 2)/100, y/30)

        return self.standing_wave_line,


#-------------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('QMK Firmata')
        self.setGeometry(100, 100, width, height)

        #-----------------------------------------------------------
        # add tabs
        tab_widget = QTabWidget()
        self.console_tab = ConsoleTab()
        self.rgb_matrix_tab = RGBMatrixTab()
        self.rgb_animation_tab = RGBAnimationTab()
        self.winfocus_tab = WinFocusListenTab()
        #self.rgb_matrix_tab = VideoPlayerTab()
        
        tab_widget.addTab(self.console_tab, 'console')
        tab_widget.addTab(self.rgb_matrix_tab, 'rgb video')
        tab_widget.addTab(self.rgb_animation_tab, 'rgb animation')
        tab_widget.addTab(self.winfocus_tab, 'layer auto switch')
        

        self.setCentralWidget(tab_widget)
        #-----------------------------------------------------------

        # setup firmata thread
        self.firmata_thread = KeybFirmataThread(port)
        self.firmata_thread.console_signal.connect(self.console_tab.update_text)
        self.firmata_thread.start()

        self.winfocus_listen_thread = WinFocusListenThread()
        self.winfocus_listen_thread.winfocus_signal.connect(self.winfocus_tab.on_winfocus)
        self.winfocus_listen_thread.start()

        self.console_tab.dbg_mask_signal.connect(self.firmata_thread.dbg_mask_set)
        self.rgb_matrix_tab.rgb_frame_signal.connect(self.firmata_thread.update_rgb)
        self.rgb_animation_tab.rgb_frame_signal.connect(self.firmata_thread.update_rgb)
        self.winfocus_tab.keyb_layer_set_signal.connect(self.firmata_thread.keyb_default_layer_set)

def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())

def list_com_ports():
    device_list = list_ports.comports()
    for device in device_list:
        print(f"{device}: vid={device.vid:04X}, pid={device.pid:04X}")
        if device.vid == VID:
            port = device.device

#-------------------------------------------------------------------------------

if __name__ == "__main__":
    #list_com_ports()
    main()
