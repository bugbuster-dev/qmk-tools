
import sys, traceback
import cv2
import numpy as np
import pyaudio

from PySide6 import QtCore
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtWidgets import QTextEdit, QPushButton, QFileDialog, QLabel, QSlider, QLineEdit, QComboBox, QSpacerItem, QSizePolicy
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QSize
from PySide6.QtCore import QRegularExpression
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtGui import QImage, QPixmap, QColor, QFont, QTextCursor, QFontMetrics, QMouseEvent, QRegularExpressionValidator, QKeyEvent

from serial.tools import list_ports

import pyfirmata2

from WinFocusListener import WinFocusListener
from FirmataKeyboard import FirmataKeyboard
from DebugTracer import DebugTracer

#-------------------------------------------------------------------------------

firmata_port        = pyfirmata2.Arduino.AUTODETECT
keyboard_vid_pid    =(0x19f5, 0x3265)

app_width       = 800
app_height      = 800

#-------------------------------------------------------------------------------

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
        self.macWinModeSelector.addItem('-')
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
    def __init__(self, rgb_matrix_size):
        self.rgb_matrix_size = rgb_matrix_size

        super().__init__()
        self.initUI()


    def initUI(self):
        self.layout = QVBoxLayout()
        self.tab_widget = QTabWidget()

        self.rgb_video_tab = RGBVideoTab(self.rgb_matrix_size)
        self.rgb_animation_tab = RGBAnimationTab(self.rgb_matrix_size)
        self.rgb_audio_tab = RGBAudioTab(self.rgb_matrix_size)

        self.tab_widget.addTab(self.rgb_video_tab, 'video')
        self.tab_widget.addTab(self.rgb_animation_tab, 'animation')
        self.tab_widget.addTab(self.rgb_audio_tab, 'audio')

        self.layout.addWidget(self.tab_widget)
        self.setLayout(self.layout)



class RGBVideoTab(QWidget):
    rgb_frame_signal = Signal(QImage, object)  # Signal to send rgb frame

    def __init__(self, rgb_matrix_size):
        super().__init__()
        self.cap = None
        self.frameRate = 25
        self.rgb_matrix_size = rgb_matrix_size
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

            keyb_rgb = p.scaled(self.rgb_matrix_size[0], self.rgb_matrix_size[1])
            #self.videoLabel.setPixmap(QPixmap.fromImage(keyb_rgb))
            self.rgb_frame_signal.emit(keyb_rgb, self.RGB_multiplier)

    def printRGBData(self, frame):
        # Example function to print RGB data of a frame
        # You might want to process or analyze this data instead of printing
        print(frame[0,0])  # Print RGB values of the top-left pixel as an example


    def closeEvent(self, event):
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
        self.timer.stop()


class AudioCaptureThread(QThread):
    def __init__(self, freq_ranges):
        super().__init__()
        self.running = False
        self.freq_ranges = freq_ranges

        self.dbg = {}
        self.dbg['DEBUG']   = DebugTracer(print=1, trace=1)

    def onPeakLevels(self, callback):
        self.callback = callback

    def run(self):
        dbg = self.dbg['DEBUG']

        FORMAT = pyaudio.paFloat32
        CHANNELS = 1
        RATE = 44100  # Sample rate
        CHUNK = 1024  # Number of audio samples per frame

        self.running = True
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)
        dbg.tr(f"audio stream {stream} opened")

        while self.running:
            duration = 0.1  # seconds
            frames = []
            for _ in range(0, int(RATE / CHUNK * duration)):
                data = stream.read(CHUNK)
                frames.append(np.frombuffer(data, dtype=np.float32))

            audio_data = np.hstack(frames)
            freq_data = np.fft.rfft(audio_data)
            freq_magnitude = np.abs(freq_data)

            # Calculate frequency bins
            freq_bins = np.fft.rfftfreq(len(audio_data), d=1./RATE)
            peak_levels = []

            for f_min, f_max in self.freq_ranges:
                # Find the bin indices corresponding to the frequency range
                idx = np.where((freq_bins >= f_min) & (freq_bins <= f_max))
                peak_level = np.max(freq_magnitude[idx])
                peak_levels.append(peak_level)

            self.callback(peak_levels)


        stream.stop_stream()
        stream.close()
        p.terminate()

    def stop(self):
        self.running = False


class RGBAudioTab(QWidget):
    rgb_frame_signal = Signal(QImage, object)  # Signal to send rgb frame

    freq_ranges = [(20, 200), (500, 2000), (2000, 4000), (4000, 6000), (6000, 8000), (8000, 10000), (10000, 20000)]

    def __init__(self, rgb_matrix_size):
        self.dbg = {}
        self.dbg['PEAK_LEVEL']  = DebugTracer(print=1, trace=1)
        self.dbg['MAX_PEAK']    = DebugTracer(print=1, trace=1)

        super().__init__()
        self.rgb_matrix_size = rgb_matrix_size
        self.RGB_multiplier = (1.0,1.0,1.0)

        self.max_levels = [10, 10, 10] # max level used for scaling
        self.max_level_running = 0# max level updated every sample
        self.sample_count = 0
        self.audioThread = AudioCaptureThread(self.freq_ranges)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        self.startButton = QPushButton("start")
        self.startButton.clicked.connect(self.start)
        layout.addWidget(self.startButton)

        self.setLayout(layout)


    #-------------------------------------------------------------------------------
    @staticmethod
    def peak_level_to_rgb(peak_levels, max_levels):
        r = g = b = 0
        try:
            r = min(peak_levels[0]/max_levels[0] * 255, 255)
            g = min(peak_levels[1]/max_levels[1] * 255, 100)
            b = min(peak_levels[2]/max_levels[2] * 255, 200)
        except:
            pass
        return r,g,b
    #-------------------------------------------------------------------------------
    def processAudioPeakLevels(self, peak_levels):
        self.sample_count += 1

        self.dbg['PEAK_LEVEL'].tr(f"peak {self.sample_count}: {peak_levels}")
        for i, lvl in enumerate(peak_levels):
            if peak_levels[i] > self.max_level_running:
                self.max_level_running = peak_levels[i]

        # update max levels every N "peak samples"
        if self.sample_count == 50:
            self.sample_count = 0
            self.max_levels = [self.max_level_running] * 3
            self.max_level_running = 0
            self.dbg['MAX_PEAK'].tr(f"max levels: {self.max_levels}")

        keyb_rgb = QImage(self.rgb_matrix_size[0], self.rgb_matrix_size[1], QImage.Format_RGB888)
        if all(level < 0.05 for (level) in peak_levels):
            # no audio
            return

        r,g,b = self.peak_level_to_rgb(peak_levels, self.max_levels)
        keyb_rgb.fill(QColor(r,g,b))

        self.rgb_frame_signal.emit(keyb_rgb, self.RGB_multiplier)

    #-------------------------------------------------------------------------------

    def start(self):
        if not self.audioThread.isRunning():
            self.audioThread.onPeakLevels(self.processAudioPeakLevels)
            self.audioThread.start()
            self.startButton.setText("stop")
        else:
            self.audioThread.stop()
            self.startButton.setText("start")


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


class LayerAutoSwitchTab(QWidget):
    keyb_layer_set_signal = Signal(int)
    num_program_selectors = 3

    def __init__(self, num_keyb_layers=8):
        self.currentLayer = 0
        self.num_keyb_layers = num_keyb_layers
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
        self.defLayerSelector.addItems([str(i) for i in range(self.num_keyb_layers)])
        layout.addWidget(self.defLayerSelector)
        self.defLayerSelector.setCurrentIndex(0)
        #self.defLayerSelector.currentIndexChanged.connect(self.on_default_layer_change)
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
        for i in range(self.num_program_selectors):
            self.programSelector.append(ProgramSelectorComboBox(self.winfocusTextEdit))
            self.programSelector[i].addItems(["" for i in range(5)])
            self.programSelector[i].setCurrentIndex(0)
            self.programSelector[i].currentIndexChanged.connect(self.on_program_selector_change)
            layout.addWidget(self.programSelector[i])

            self.layerSelector.append(QComboBox())
            self.layerSelector[i].addItems([str(i) for i in range(self.num_keyb_layers)])
            self.layerSelector[i].setCurrentIndex(0)
            layout.addWidget(self.layerSelector[i])

        #---------------------------------------
        self.setLayout(layout)

        # Connect winfocusTextEdit mouse press event
        self.winfocusTextEdit.mousePressEvent = self.selectLine

    # this python program has focus and only relevant if python program was selected to use separate layer and is now unselected
    # which is not a likely use case.
    def on_program_selector_change(self, index):
        pass
        #for i in range(self.num_program_selectors):
            #if self.sender() == self.programSelector[i]:
                #pass


    def on_winfocus(self, line):
        self.updateWinfocusText(line)
        self.currentFocus = line

        layerSet = False

        # foreground focus window info
        focus_win = line.split("\t")
        #print(f"on_winfocus {focus_win}")
        for i, ps in enumerate(self.programSelector):
            compare_win = self.programSelector[i].currentText().split("\t")
            #print(f"on_winfocus compare: {compare_win}")
            if focus_win[0].strip() == compare_win[0].strip() and \
               focus_win[1].strip() == compare_win[1].strip():
                layer = int(self.layerSelector[i].currentText())
                self.keyb_layer_set_signal.emit(layer)
                self.currentLayer = layer
                layerSet = True

        if layerSet:
            return

        defaultLayer = self.defLayerSelector.currentIndex()
        if self.currentLayer != defaultLayer:
            self.keyb_layer_set_signal.emit(defaultLayer)
            self.currentLayer = defaultLayer

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

    def __init__(self, rgb_matrix_size):
        super().__init__()
        self.initUI()
        self.rgb_matrix_size = rgb_matrix_size

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


    print_canvas_size = 0
    def captureAnimationFrame(self):
        if self.ani == None:
            return

        self.ani.pause()

        self.canvas.draw()
        buffer = np.frombuffer(self.canvas.buffer_rgba(), dtype=np.uint8)
        width, height = self.figure.get_size_inches() * self.figure.get_dpi()
        if self.print_canvas_size:
            print(f"canvas size: {width}x{height}")
            self.print_canvas_size = 0
        img = buffer.reshape(int(height), int(width), 4)
        img = rgba2rgb(img)
        qimage = QImage(img.data, width, height, QImage.Format_RGB888)
        keyb_rgb = qimage.scaled(self.rgb_matrix_size[0], self.rgb_matrix_size[1])
        self.rgb_frame_signal.emit(keyb_rgb, (1.0,1.0,1.0))

        self.ani.resume()

    def _animate(self, i):
        ret = self.animate(i)
        if i == self.frames:
            self.figure.clear()
        return ret

#-------------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('QMK Firmata')
        self.setGeometry(100, 100, app_width, app_height)
        self.setFixedSize(app_width, app_height)

        # instantiate firmata keyboard
        self.keyboard = FirmataKeyboard(port=firmata_port, vid_pid=keyboard_vid_pid)
        rgb_matrix_size = self.keyboard.rgb_matrix_size()
        num_keyb_layers = self.keyboard.num_layers()

        #-----------------------------------------------------------
        # add tabs
        tab_widget = QTabWidget()
        self.layer_switch_tab = LayerAutoSwitchTab(num_keyb_layers)
        self.console_tab = ConsoleTab()
        self.rgb_matrix_tab = RGBMatrixTab(rgb_matrix_size)

        tab_widget.addTab(self.console_tab, 'console')
        tab_widget.addTab(self.rgb_matrix_tab, 'rgb matrix')
        tab_widget.addTab(self.layer_switch_tab, 'layer auto switch')

        self.setCentralWidget(tab_widget)
        #-----------------------------------------------------------

        self.keyboard.signal_console_output.connect(self.console_tab.update_text)
        self.keyboard.signal_debug_mask.connect(self.console_tab.update_debug_mask)
        self.keyboard.signal_macwin_mode.connect(self.console_tab.update_macwin_mode)

        self.winfocus_listener = WinFocusListener()
        self.winfocus_listener.winfocus_signal.connect(self.layer_switch_tab.on_winfocus)
        self.winfocus_listener.start()

        self.console_tab.signal_dbg_mask.connect(self.keyboard.keyb_dbg_mask_set)
        self.console_tab.signal_macwin_mode.connect(self.keyboard.keyb_macwin_mode_set)
        self.rgb_matrix_tab.rgb_video_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.rgb_matrix_tab.rgb_animation_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.rgb_matrix_tab.rgb_audio_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.layer_switch_tab.keyb_layer_set_signal.connect(self.keyboard.keyb_default_layer_set)

        self.keyboard.start()

    def closeEvent(self, event):
        self.winfocus_listener.terminate()
        self.keyboard.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())

def list_com_ports(vid = None, pid = None):
    device_list = list_ports.comports()
    for device in device_list:
        print(f"{device}: vid={device.vid:04x}, pid={device.pid:04x}")
        if device.vid == vid and (pid == None or device.pid == pid):
            port = device.device

#-------------------------------------------------------------------------------

if __name__ == "__main__":
    #list_com_ports()
    main()
