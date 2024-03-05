
import sys, traceback
import cv2
import numpy as np

from PySide6 import QtCore
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QFileDialog, QLabel, QSlider
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QSize
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QImage, QPixmap, QColor, QFont

import serial
from serial.tools import list_ports

import pyfirmata2
import time

#-------------------------------------------------------------------------------

port        = ""
baudrate    = 115200

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
        
        
class NuphyAir96V2:
    RGB_MATRIX_CMD = 0x01
    
    RGB_MAXTRIX_W = 19
    RGB_MAXTRIX_H = 6

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

    def __init__(self, port, baudrate):
        self.port = port
        super().__init__()

    def console_line_handler(self, *data):
        line = pyfirmata2.util.two_byte_iter_to_str(data)
        if line:
            self.console_signal.emit(line)  # Emit signal with the received line

    def update_rgb(self, img, rgb_multiplier):
        if self.board == None:
            return

        #print(rgb_multiplier)

        print_pixeldata = 0
        if print_pixeldata:
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
                rgb_pixel = NuphyAir96V2.pixel_to_rgb_index_duration(pixel, NuphyAir96V2.xy_to_rgb_index(x, y), 200, rgb_multiplier)
                data.extend(rgb_pixel)

                if print_pixeldata:
                    print(f"{x:2},{y:2}=({pixel[0]:3},{pixel[1]:3},{pixel[2]:3})", end=" ")
                    print_buffer(rgb_pixel)

                if len(data) >= self.MAX_LEN_SYSEX_DATA:
                    self.board.send_sysex(NuphyAir96V2.RGB_MATRIX_CMD, data)
                    data = bytearray()
        
        if len(data) > 0:
            self.board.send_sysex(NuphyAir96V2.RGB_MATRIX_CMD, data)

    
    def run(self):
        self.port =  pyfirmata2.Arduino.AUTODETECT
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
        #self.board.send_sysex(NuphyAir96V2.RGB_MATRIX_CMD, data)
        while True:
            time.sleep(0.1)


class ConsoleTab(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)

        font = QFont()
        font.setFamily("Courier New");
        self.text_edit.setFont(font);

        layout.addWidget(self.text_edit)
        self.setLayout(layout)

    def update_text(self, text):
        self.text_edit.insertPlainText(text)

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
            
            keyb_rgb = p.scaled(NuphyAir96V2.RGB_MAXTRIX_W, NuphyAir96V2.RGB_MAXTRIX_H)
            #self.videoLabel.setPixmap(QPixmap.fromImage(keyb_rgb))
            self.rgb_frame_signal.emit(keyb_rgb, self.RGB_multiplier)

    def printRGBData(self, frame):
        # Example function to print RGB data of a frame
        # You might want to process or analyze this data instead of printing
        print(frame[0,0])  # Print RGB values of the top-left pixel as an example


#-------------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('QMK Firmata')
        self.setGeometry(100, 100, width, height)

        tab_widget = QTabWidget()
        self.console_tab = ConsoleTab()
        self.rgb_matrix_tab = RGBMatrixTab()
        #self.rgb_matrix_tab = VideoPlayerTab()
        
        tab_widget.addTab(self.console_tab, 'console')
        tab_widget.addTab(self.rgb_matrix_tab, 'rgb matrix')

        self.setCentralWidget(tab_widget)

        # Setup firmata thread
        self.firmata_thread = KeybFirmataThread(port, baudrate)
        self.firmata_thread.console_signal.connect(self.console_tab.update_text)
        self.firmata_thread.start()

        self.rgb_matrix_tab.rgb_frame_signal.connect(self.firmata_thread.update_rgb)

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
