import sys, time, hid, argparse
import cv2, pyaudio, numpy as np

from PySide6 import QtCore
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtWidgets import QTextEdit, QPushButton, QFileDialog, QLabel, QSlider, QLineEdit
from PySide6.QtWidgets import QCheckBox, QComboBox, QSpacerItem, QSizePolicy, QMessageBox
from PySide6.QtCore import Qt, QThread, Signal, QTimer #, QSize, QUrl
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QImage, QPixmap, QColor, QFont, QTextCursor, QFontMetrics, QMouseEvent, QKeyEvent, QKeySequence
from PySide6.QtGui import QRegularExpressionValidator, QIntValidator, QDoubleValidator
#from PySide6.QtMultimedia import QMediaPlayer
#from PySide6.QtMultimediaWidgets import QVideoWidget

from WinFocusListener import WinFocusListener
from FirmataKeyboard import FirmataKeyboard
from DebugTracer import DebugTracer

from windowcapture import WindowCapture

import asyncio
import websockets

#-------------------------------------------------------------------------------

app_width       = 800
app_height      = 1000

#-------------------------------------------------------------------------------


class WSServer(QThread):

    def __init__(self, msg_handler, port = 8765):
        self.dbg = {}
        self.dbg['DEBUG'] = DebugTracer(print=1, trace=1, obj=self)

        self.port = port
        self.loop = None
        self.msg_handler = msg_handler
        super().__init__()

    def run(self):
        self.dbg['DEBUG'].tr(f"ws server start on port: {self.port}")
        asyncio.run(self.ws_main())

    async def ws_main(self):
        self.loop = asyncio.get_running_loop()
        self.stop_ev = self.loop.create_future()
        async with websockets.serve(self.msg_handler, "localhost", self.port):
            await self.stop_ev
        self.dbg['DEBUG'].tr("ws server ended")

    async def ws_close(self):
        # dummy connect to exit ws_main
        try:
            async with websockets.connect(f"ws://localhost:{self.port}") as websocket:
                await websocket.send("")
        except Exception as e:
            pass

    def stop(self):
        #self.dbg['DEBUG'].tr("ws server stop")
        if self.loop:
            self.stop_ev.set_result(None)
            asyncio.run(self.ws_close())


class ConsoleTab(QWidget):
    signal_dbg_mask = Signal(int)
    signal_macwin_mode = Signal(str)
    signal_dynld_function = Signal(int, bytearray)

    def __init__(self):
        super().__init__()
        self.initUI()

    def update_keyb_dbg_mask(self):
        dbg_mask = int(self.dbgMaskInput.text(),16)
        self.signal_dbg_mask.emit(dbg_mask)

    def update_keyb_macwin_mode(self):
        macwin_mode = self.macWinModeSelector.currentText()
        self.signal_macwin_mode.emit(macwin_mode)

    def update_keyb_dynld_test_fun(self):
        DYNLD_TEST_FUNC = 1
        bin_file = 'V:\\shared\\nuphy\\custom_testfunc.bin'
        # Open the file in binary read mode and read its contents into a bytearray
        with open(bin_file, 'rb') as file:
            buf = bytearray(file.read())
            self.signal_dynld_function.emit(DYNLD_TEST_FUNC, buf)

    def initUI(self):
        hLayout = QHBoxLayout()
        dbgMaskLabel = QLabel("debug mask")
        metrics = QFontMetrics(dbgMaskLabel.font())
        dbgMaskLabel.setFixedHeight(metrics.height())

        #---------------------------------------
        # debug mask hex byte input
        self.dbgMaskInput = QLineEdit()
        # Set a validator to allow only hex characters (0-9, A-F, a-f) and limit to 2 characters
        regExp = QRegularExpression("[0-9A-Fa-f]{1,2}")
        self.dbgMaskInput.setValidator(QRegularExpressionValidator(regExp))
        metrics = QFontMetrics(self.dbgMaskInput.font())
        width = metrics.horizontalAdvance('W') * 3  # 'W' is used as it's typically the widest character
        self.dbgMaskInput.setFixedWidth(width)

        self.dbgMaskUpdateButton = QPushButton("set")
        self.dbgMaskUpdateButton.clicked.connect(self.update_keyb_dbg_mask)
        self.dbgMaskUpdateButton.setFixedWidth(width)

        hLayout.addWidget(dbgMaskLabel)
        hLayout.addWidget(self.dbgMaskInput)
        hLayout.addWidget(self.dbgMaskUpdateButton)
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)  # Set the frame shape to a vertical line
        hLayout.addWidget(separator)

        #---------------------------------------
        # dynld test function
        self.dynldTestFunButton = QPushButton("dynld test")
        self.dynldTestFunButton.clicked.connect(self.update_keyb_dynld_test_fun)

        hLayout.addWidget(self.dynldTestFunButton)
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)  # Set the frame shape to a vertical line
        hLayout.addWidget(separator)

        #---------------------------------------
        # mac/win mode
        macWinLabel = QLabel("mac/win mode")
        self.macWinModeSelector = QComboBox()
        self.macWinModeSelector.addItem('m')
        self.macWinModeSelector.addItem('w')
        self.macWinModeSelector.addItem('-')
        hLayout.addWidget(macWinLabel)
        hLayout.addWidget(self.macWinModeSelector)
        self.macWinModeSelector.setCurrentIndex(1)
        self.macWinModeSelector.currentIndexChanged.connect(self.update_keyb_macwin_mode)
        self.macWinModeSelector.setFixedWidth(width)

        #---------------------------------------
        # console output
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
        cursor = self.console_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.console_output.setTextCursor(cursor)
        self.console_output.insertPlainText(text)
        self.console_output.ensureCursorVisible()

    def update_debug_mask(self, dbg_mask):
        self.dbgMaskInput.setText(f"{dbg_mask:02x}")

    def update_macwin_mode(self, macwin_mode):
        self.macWinModeSelector.setCurrentIndex(0 if macwin_mode == 'm' else 1)

#-------------------------------------------------------------------------------

class RGBMatrixTab(QWidget):
    signal_rgb_matrix_mode = Signal(int)

    def __init__(self, rgb_matrix_size):
        self.rgb_matrix_size = rgb_matrix_size

        super().__init__()
        self.initUI()

    def update_keyb_rgb_matrix_mode(self):
        matrix_mode = int(self.rgbMatrixModeInput.text())
        self.signal_rgb_matrix_mode.emit(matrix_mode)

    def update_rgb_matrix_mode(self, matrix_mode):
        self.rgbMatrixModeInput.setText(f"{matrix_mode}")

    def initUI(self):
        self.layout = QVBoxLayout()
        hLayout = QHBoxLayout()
        self.tab_widget = QTabWidget()

        #---------------------------------------
        # rgb matrix mode
        rgbMaxtrixModeLabel = QLabel("rgb matrix mode")
        self.rgbMatrixModeInput = QLineEdit()
        regExp = QRegularExpression("[0-9]{1,2}")
        self.rgbMatrixModeInput.setValidator(QRegularExpressionValidator(regExp))
        metrics = QFontMetrics(self.rgbMatrixModeInput.font())
        width = metrics.horizontalAdvance('W') * 3  # 'W' is used as it's typically the widest character
        self.rgbMatrixModeInput.setFixedWidth(width)

        self.rgbModeUpdateButton = QPushButton("set")
        self.rgbModeUpdateButton.clicked.connect(self.update_keyb_rgb_matrix_mode)
        self.rgbModeUpdateButton.setFixedWidth(width)

        hLayout.addWidget(rgbMaxtrixModeLabel)
        hLayout.addWidget(self.rgbMatrixModeInput)
        hLayout.addWidget(self.rgbModeUpdateButton)
        hLayout.addStretch(1)

        #---------------------------------------
        self.rgb_video_tab = RGBVideoTab(self, self.rgb_matrix_size)
        self.rgb_animation_tab = RGBAnimationTab(self.rgb_matrix_size)
        self.rgb_audio_tab = RGBAudioTab(self.rgb_matrix_size)
        self.rgb_capture_tab = RGBWinCaptureTab(self.rgb_matrix_size)
        self.rgb_dynld_animation_tab = RGBDynLDAnimationTab()

        self.tab_widget.addTab(self.rgb_video_tab, 'video')
        self.tab_widget.addTab(self.rgb_animation_tab, 'animation')
        self.tab_widget.addTab(self.rgb_audio_tab, 'audio')
        self.tab_widget.addTab(self.rgb_capture_tab, 'capture')
        self.tab_widget.addTab(self.rgb_dynld_animation_tab, 'dynld animation')

        self.layout.addLayout(hLayout)
        self.layout.addWidget(self.tab_widget)
        self.setLayout(self.layout)

#-------------------------------------------------------------------------------

class RGBVideoTab(QWidget):
    rgb_frame_signal = Signal(QImage, object)  # Signal to send rgb frame

    def __init__(self, rgb_matrix_tab, rgb_matrix_size):
        self.dbg = {}
        self.dbg['DEBUG'] = DebugTracer(print=0, trace=1, obj=self)
        super().__init__()

        self.rgb_matrix_tab = rgb_matrix_tab
        self.cap = None
        self.frameRate = 25
        self.rgb_matrix_size = rgb_matrix_size
        self.RGB_multiplier = (1.0,1.0,1.0)
        self.initUI()

    async def ws_handler(self, websocket, path):
        try:
            async for message in websocket:
                try:
                    message = bytearray(message, 'utf-8')
                except:
                    pass # already bytearray

                self.dbg['DEBUG'].tr(f"ws_handler: {message}")
                sub = b"rgb."
                if message.startswith(sub):
                    message = message[len(sub):]
                    subs = [ b"mode:", b"img:" ]
                    for sub in subs:
                        if message.startswith(sub):
                            if sub == b"mode:":
                                try:
                                    mode = int(message.split(b":")[1])
                                    self.rgb_matrix_tab.signal_rgb_matrix_mode.emit(mode)
                                except Exception as e:
                                    self.dbg['DEBUG'].tr(f"ws_handler: {e}")
                            if sub == b"img:":
                                data = message[len(sub):]
                                w = self.rgb_matrix_size[0]
                                h = self.rgb_matrix_size[1]
                                #self.dbg['DEBUG'].tr(f"ws_handler:{w}x{h} {data}")

                                img = QImage(w, h, QImage.Format_RGB888)
                                img.fill(QColor('black'))
                                for y in range(h):
                                    for x in range(w):
                                        index = (y * w + x) * 3
                                        try:
                                            red, green, blue = data[index], data[index + 1], data[index + 2]
                                            img.setPixelColor(x, y, QColor(red, green, blue))
                                        except Exception as e:
                                            #self.dbg['DEBUG'].tr(f"ws_handler: {e}")
                                            pass

                                self.rgb_frame_signal.emit(img, self.RGB_multiplier)
                                self.dbg['DEBUG'].tr(f"ws_handler:emit(img) done")
                self.dbg['DEBUG'].tr(f"ws_handler: message handled")
                await asyncio.sleep(0)  # Ensures control is yielded back to the event loop

        except Exception as e:
            self.dbg['DEBUG'].tr(f"ws_handler: {e}")
        self.dbg['DEBUG'].tr(f"ws_handler: done")

    def wsServerStartStop(self, state):
        #self.dbg['DEBUG'].tr(f"{state}")
        if Qt.CheckState(state) == Qt.CheckState.Checked:
            self.dbg['DEBUG'].tr("ws server start")
            self.wsServer = WSServer(self.ws_handler, int(self.wsServerPort.text()))
            self.wsServer.start()
        else:
            try:
                self.wsServer.stop()
                self.wsServer.wait()
                self.wsServer = None
            except Exception as e:
                self.dbg['DEBUG'].tr(f"{e}")

    def initUI(self):
        self.layout = QVBoxLayout()
        self.videoLabel = QLabel("")
        self.videoLabel.setFixedSize(app_width, app_height)
        self.videoLabel.setAlignment(Qt.AlignTop)

        hlayout = QHBoxLayout()
        self.openButton = QPushButton("open file")
        self.openButton.setFixedWidth(100)
        self.openButton.clicked.connect(self.openFile)
        #---------------------------------------
        #region "rgb video ws server" enable checkbox plus port input
        self.wsServerCheckbox = QCheckBox("enable ws server", self)
        self.wsServerPort = QLineEdit("8787")
        port_validator = QIntValidator(0, 65535, self)
        self.wsServerPort.setValidator(port_validator)
        self.wsServerPort.setFixedWidth(50)
        self.wsServerCheckbox.stateChanged.connect(self.wsServerStartStop)
        hlayout = QHBoxLayout()
        hlayout.addStretch(1)
        hlayout.addWidget(self.wsServerCheckbox)
        hlayout.addWidget(self.wsServerPort)
        #endregion

        controlsLayout = QHBoxLayout()
        self.frameRateLabel = QLabel("frame rate")
        self.framerateSlider = QSlider(Qt.Horizontal)
        self.framerateSlider.setMinimum(1)  # Minimum framerate
        self.framerateSlider.setMaximum(120)  # Maximum framerate
        self.framerateSlider.setValue(self.frameRate)  # Set the default value
        self.framerateSlider.setTickInterval(1)  # Set tick interval
        self.framerateSlider.setTickPosition(QSlider.TicksBelow)
        self.framerateSlider.setToolTip("frame rate")
        self.framerateSlider.valueChanged.connect(self.adjustFramerate)

        #region framerate/RGB multiplier sliders
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
        #endregion

        self.layout.addLayout(hlayout)
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
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
            self.timer.stop()
            self.rgb_frame_signal.emit(None, self.RGB_multiplier)
            self.openButton.setText("open file")
            return

        fileName, _ = QFileDialog.getOpenFileName(self, "open file", "", "Video Files (*.mp4 *.avi *.mov *.webm *.gif)")
        if fileName:
            self.cap = cv2.VideoCapture(fileName)
            fps = self.cap.get(cv2.CAP_PROP_FPS)  # Get the video's frame rate
            self.frameRate = fps if fps > 0 else 25
            self.framerateSlider.setValue(int(self.frameRate))
            self.timer.start(1000 / self.frameRate)
            self.openButton.setText("stop")

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
        else:
            #print("Reached the end of the video, restarting...")
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Rewind the video

    def printRGBData(self, frame):
        # Example function to print RGB data of a frame
        # You might want to process or analyze this data instead of printing
        print(frame[0,0])  # Print RGB values of the top-left pixel as an example


    def closeEvent(self, event):
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
        self.timer.stop()


#-------------------------------------------------------------------------------

class AudioCaptureThread(QThread):

    def __init__(self, freq_ranges, interval):
        super().__init__()
        self.running = False
        self.freq_ranges = freq_ranges
        self.interval = interval

        self.dbg = {}
        self.dbg['DEBUG']   = DebugTracer(print=1, trace=1)

    def connect_callback(self, callback):
        self.callback = callback

    def set_freq_ranges(self, freq_ranges):
        self.freq_ranges = freq_ranges

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
            duration = self.interval  # seconds
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
                if len(freq_magnitude[idx]) > 0:
                    peak_level = np.max(freq_magnitude[idx])
                    peak_levels.append(peak_level)

            self.callback(peak_levels)

        stream.stop_stream()
        stream.close()
        dbg.tr(f"audio stream {stream} closed")
        p.terminate()
        self.callback(None)

    def stop(self):
        self.running = False


class RGBAudioTab(QWidget):
    rgb_frame_signal = Signal(QImage, object)  # Signal to send rgb frame

    freq_ranges = []

    @staticmethod
    def freq_subranges(freq_low, freq_high, num_ranges):
        freq_range = []
        step = (freq_high - freq_low)/num_ranges
        for i in range(num_ranges):
            freq_range.append((freq_low + i*step, freq_low + (i+1)*step))

        return freq_range


    def __init__(self, rgb_matrix_size):
        #-----------------------------------------------------------
        self.dbg = {}
        self.dbg['DEBUG']       = DebugTracer(print=1, trace=1)
        self.dbg['FREQ_RANGE']  = DebugTracer(print=1, trace=1)
        self.dbg['PEAK_LEVEL']  = DebugTracer(print=0, trace=1)
        self.dbg['MAX_PEAK']    = DebugTracer(print=1, trace=1)
        #-----------------------------------------------------------

        super().__init__()
        self.initUI()

        #-----------------------------------------------------------
        self.rgb_matrix_size = rgb_matrix_size
        self.keyb_rgb = QImage(self.rgb_matrix_size[0], self.rgb_matrix_size[1], QImage.Format_RGB888)
        self.keyb_rgb_mask = QImage(self.keyb_rgb.size(), QImage.Format_Grayscale8)
        self.keyb_rgb_mask_mode = 0

        self.RGB_multiplier = (1.0,1.0,1.0)

        self.max_level = 10  # max level used for rgb intensity
        self.max_level_running = 0  # max level updated every sample
        self.sample_count = 0
        self.audioThread = AudioCaptureThread(self.freq_ranges, 0.08)

    def initUI(self):
        layout = QVBoxLayout()
        layout.addStretch(1)

        freqRangeLayout = QHBoxLayout()
        # frequency range input
        self.freqRangeLabel = QLabel("frequency range")
        self.freqRangeLowInput = QLineEdit()
        self.frequencyHighInput = QLineEdit()
        self.freqRangeLowInput.setValidator(QIntValidator(0,20000))
        self.frequencyHighInput.setValidator(QIntValidator(0,20000))
        self.freqRangeLabel.setFixedWidth(100)
        self.freqRangeLowInput.setFixedWidth(50)
        self.frequencyHighInput.setFixedWidth(50)
        self.freqRangeLowInput.setText("0")
        self.frequencyHighInput.setText("1600")
        self.freqRangeLowInput.textChanged.connect(self.update_freq_ranges)
        self.frequencyHighInput.textChanged.connect(self.update_freq_ranges)

        self.nSubRangesLabel = QLabel("#subranges")
        self.nSubRangesInput = QLineEdit()
        self.nSubRangesInput.setValidator(QIntValidator(1,16))
        self.nSubRangesLabel.setFixedWidth(80)
        self.nSubRangesInput.setFixedWidth(50)
        self.nSubRangesInput.setText("16")
        self.nSubRangesInput.textChanged.connect(self.update_freq_ranges)

        self.maxLevelLabel = QLabel("max level (0 for auto)")
        self.maxLevelInput = QLineEdit()
        self.maxLevelInput.setValidator(QIntValidator(0,100))
        self.maxLevelLabel.setFixedWidth(120)
        self.maxLevelInput.setFixedWidth(50)
        self.maxLevelInput.setText("0")

        freqRangeLayout.addWidget(self.freqRangeLabel)
        freqRangeLayout.addWidget(self.freqRangeLowInput)
        freqRangeLayout.addWidget(self.frequencyHighInput)
        freqRangeLayout.addWidget(self.nSubRangesLabel)
        freqRangeLayout.addWidget(self.nSubRangesInput)

        freqRangeLayout.addWidget(self.maxLevelLabel)
        freqRangeLayout.addWidget(self.maxLevelInput)

        freqRangeLayout.addStretch(1)
        layout.addLayout(freqRangeLayout)

        #-------------------------------------------------------------------------------
        num_subranges = 16
        range_red_values =      [ 3.0, 2.0, 1.4, 1.0, 0.4, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 2.0, 3.0 ]
        range_green_values =    [ 0.0, 0.2, 0.6, 0.8, 0.8, 1.2, 1.6, 2.0, 2.0, 1.6, 1.2, 0.8, 0.4, 0.0, 0.0, 0.0 ]
        range_blue_values =     [ 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.4, 0.6, 1.0, 1.2, 1.8, 2.0, 3.0 ]

        redRangeLayout = QHBoxLayout()
        self.redRangeLabel = QLabel("r")
        self.redRangeInput = []
        redRangeLayout.addWidget(self.redRangeLabel)
        for i in range(num_subranges):
            self.redRangeInput.append(QLineEdit())
            self.redRangeInput[i].setValidator(QDoubleValidator(0.0,5.0,1))
            self.redRangeInput[i].setText(str(range_red_values[i]))
            self.redRangeInput[i].textChanged.connect(self.update_freq_rgb)
            redRangeLayout.addWidget(self.redRangeInput[i])

        greenRangeLayout = QHBoxLayout()
        self.greenRangeLabel = QLabel("g")
        self.greenRangeInput = []
        greenRangeLayout.addWidget(self.greenRangeLabel)
        for i in range(num_subranges):
            self.greenRangeInput.append(QLineEdit())
            self.greenRangeInput[i].setValidator(QDoubleValidator(0.0,5.0,1))
            self.greenRangeInput[i].setText(str(range_green_values[i]))
            self.greenRangeInput[i].textChanged.connect(self.update_freq_rgb)
            greenRangeLayout.addWidget(self.greenRangeInput[i])

        blueRangeLayout = QHBoxLayout()
        self.blueRangeLabel = QLabel("b")
        self.blueRangeInput = []
        blueRangeLayout.addWidget(self.blueRangeLabel)
        for i in range(num_subranges):
            self.blueRangeInput.append(QLineEdit())
            self.blueRangeInput[i].setValidator(QDoubleValidator(0.0,5.0,1))
            self.blueRangeInput[i].setText(str(range_blue_values[i]))
            self.blueRangeInput[i].textChanged.connect(self.update_freq_rgb)
            blueRangeLayout.addWidget(self.blueRangeInput[i])

        layout.addLayout(redRangeLayout)
        layout.addLayout(greenRangeLayout)
        layout.addLayout(blueRangeLayout)

        #-------------------------------------------------------------------------------
        self.startButton = QPushButton("start")
        self.startButton.clicked.connect(self.start)
        layout.addWidget(self.startButton)

        self.setLayout(layout)


    def update_freq_rgb(self):
        n_ranges = int(self.nSubRangesInput.text())
        self.freq_rgb_r = [float(self.redRangeInput[i].text()) for i in range(n_ranges)]
        self.freq_rgb_g = [float(self.greenRangeInput[i].text()) for i in range(n_ranges)]
        self.freq_rgb_b = [float(self.blueRangeInput[i].text()) for i in range(n_ranges)]

    def update_freq_ranges(self):
        self.freq_ranges = self.freq_subranges(int(self.freqRangeLowInput.text()), int(self.frequencyHighInput.text()), int(self.nSubRangesInput.text()))
        self.dbg['FREQ_RANGE'].tr(f"audio peak freq range {self.freq_ranges}")
        self.audioThread.set_freq_ranges(self.freq_ranges)

    #-------------------------------------------------------------------------------
    def peak_level_to_rgb(self, peak_levels, max_level):
        r = g = b = 0

        for i in range(len(peak_levels)):
            r += peak_levels[i] * self.freq_rgb_r[i]
            g += peak_levels[i] * self.freq_rgb_g[i]
            b += peak_levels[i] * self.freq_rgb_b[i]

        r /= 3
        g /= 3
        b /= 3

        # red for low, green for mid, blue for high tones
        r = min(r/max_level * 255, 255)
        g = min(g/max_level * 255, 255)
        b = min(b/max_level * 255, 255)

        return r,g,b

    #-------------------------------------------------------------------------------
    def processAudioPeakLevels(self, peak_levels):
        if peak_levels is None:
            self.rgb_frame_signal.emit(None, self.RGB_multiplier)
            return

        self.sample_count += 1
        self.dbg['PEAK_LEVEL'].tr(f"peak {self.sample_count}: {peak_levels}")

        # update "running max level", after N samples "max level" is adjusted with this
        peak_level = 0 # current sample peak level
        for i, lvl in enumerate(peak_levels):
            if lvl > self.max_level_running:
                self.max_level_running = lvl
            if lvl > peak_level:
                peak_level = lvl

        # update "max level" every N samples, brightness is based on current peak levels and "max level"
        if self.sample_count == 30:
            self.sample_count = 0
            max_level_input = 0
            try:
                max_level_input = int(self.maxLevelInput.text())
            except:
                pass

            if max_level_input > 0: # user defined max level
                self.max_level = max_level_input
            else:
                self.max_level += (self.max_level_running - self.max_level)/2

            self.dbg['MAX_PEAK'].tr(f"max level: {self.max_level_running} ({self.max_level})")
            self.max_level_running = 0

        if all(level < 0.05 for (level) in peak_levels):
            # no audio
            return

        r,g,b = self.peak_level_to_rgb(peak_levels, self.max_level)
        self.keyb_rgb.fill(QColor(r,g,b))

        #-----------------------------------------------------------
        # mask image to disable leds depending on peak level
        if self.keyb_rgb_mask_mode != 0:
            img = self.keyb_rgb.convertToFormat(QImage.Format_ARGB32)
            self.keyb_rgb_mask.fill(0)
            mask_bits = self.keyb_rgb_mask.bits()
            bytes_per_line = self.keyb_rgb_mask.bytesPerLine()

            # max num leds to light up to left and right of center
            peak_max_num_leds = int(img.width()//2)
            center_led = int(img.width()//2)
            num_leds = int(min(1.0, peak_level / self.max_level) * peak_max_num_leds)
            x_range = (max(0, center_led - num_leds), min(img.width(), center_led + num_leds)+1)

            if self.keyb_rgb_mask_mode == 1:
                for x in range(x_range[0], x_range[1]):
                    # lines 2,3
                    mask_bits[2 * bytes_per_line + x] = 255
                    mask_bits[3 * bytes_per_line + x] = 255

            if self.keyb_rgb_mask_mode == 2:
                for x in range(x_range[0], x_range[1]):
                    # all lines
                    for i in range(img.height()):
                        mask_bits[i * bytes_per_line + x] = 255

            img.setAlphaChannel(self.keyb_rgb_mask)
            img = img.convertedTo(QImage.Format_RGB888)
            self.keyb_rgb = img

        #-----------------------------------------------------------
        #self.dbg['DEBUG'].tr(f"send rgb {self.keyb_rgb}")
        if self.running:
            self.rgb_frame_signal.emit(self.keyb_rgb, self.RGB_multiplier)

    #-------------------------------------------------------------------------------

    def start(self):
        if not self.audioThread.isRunning():
            self.running = True
            self.update_freq_rgb()
            self.update_freq_ranges()
            self.audioThread.connect_callback(self.processAudioPeakLevels)
            self.audioThread.start()
            self.startButton.setText("stop")
        else:
            self.running = False
            self.audioThread.stop()
            self.audioThread.wait()
            self.startButton.setText("start")

    def closeEvent(self, event):
        if self.audioThread.isRunning():
            self.audioThread.stop()
            self.audioThread.wait()

#-------------------------------------------------------------------------------

class RGBWinCaptureTab(QWidget):
    rgb_frame_signal = Signal(QImage, object)  # Signal to send rgb frame

    class WindowSelectorComboBox(QComboBox):

        def __init__(self, parent):
            self.parent = parent
            super().__init__(None)

        def mousePressEvent(self, event: QMouseEvent):
            if event.button() == Qt.LeftButton:
                self.clear()
                window_names = self.parent.list_windows()
                for name in window_names:
                    if name[1]:
                        self.addItems([name[1]])

            # Call the base class implementation to ensure default behavior
            super().mousePressEvent(event)


    class WindowCaptureThread(QThread):
        def __init__(self, window_name, window_off_size, resize, interval):
            self.dbg = {}
            self.dbg['DEBUG'] = DebugTracer(print=1, trace=1)

            self.running = False
            self.window_name = window_name
            self.window_off_size = window_off_size
            self.resize = resize
            self.interval = interval
            super().__init__()

        def connect_callback(self, callback):
            self.callback = callback

        def run(self):
            dbg = self.dbg['DEBUG']

            self.running = True
            self.windowcapture = WindowCapture(window_name=self.window_name)
            try:
                img = self.windowcapture.get_screenshot()
                h, w, ch = img.shape
                dbg.tr(f"window capture img shape: {w}x{h} {ch}")
            except Exception as e:
                pass

            self.update_off_size(self.window_off_size)
            while self.running:
                try:
                    img = self.windowcapture.get_screenshot()
                    h, w, ch = img.shape
                    bytesPerLine = w*ch
                    qimage = QImage(img.data, w, h, bytesPerLine, QImage.Format_BGR888)
                    keyb_rgb = qimage.scaled(self.resize[0], self.resize[1])
                    #keyb_rgb = keyb_rgb.convertToFormat(QImage.Format_RGB888)
                    self.callback(keyb_rgb)
                except Exception as e:
                    dbg.tr(f"error: {e}")
                    break

                time.sleep(self.interval)

            self.callback(None)
            dbg.tr(f"window capture thread stopped")


        def update_off_size(self, window_off_size):
            self.window_off_size = window_off_size
            if self.windowcapture:
                self.windowcapture.update_off_size(window_off_size)

        def stop(self):
            self.running = False


    def __init__(self, rgb_matrix_size):
        #-----------------------------------------------------------
        self.dbg = {}
        self.dbg['DEBUG']       = DebugTracer(print=1, trace=1)
        #-----------------------------------------------------------
        self.rgb_matrix_size = rgb_matrix_size
        self.windowCaptureThread = None

        super().__init__()
        self.initUI()

    def list_windows(self):
        window_names = WindowCapture.list_window_names()
        return window_names

    def initUI(self):
        layout = QVBoxLayout()
        layout.addStretch(1)

        #---------------------------------------
        hlayout = QHBoxLayout()
        hlayout.addStretch(1)
        capturePosLabel = QLabel("select window to capture below and select x,y,w,h of this window")
        self.capturePosX = QLineEdit()
        self.capturePosY = QLineEdit()
        self.captureWidth = QLineEdit()
        self.captureHeight = QLineEdit()
        self.capturePosX.setValidator(QIntValidator())
        self.capturePosY.setValidator(QIntValidator())
        self.captureWidth.setValidator(QIntValidator())
        self.captureHeight.setValidator(QIntValidator())
        self.capturePosX.setText("0")
        self.capturePosY.setText("0")
        self.captureWidth.setText("360")
        self.captureHeight.setText("280")
        self.capturePosX.setFixedWidth(50)
        self.capturePosY.setFixedWidth(50)
        self.captureWidth.setFixedWidth(50)
        self.captureHeight.setFixedWidth(50)
        hlayout.addWidget(capturePosLabel)
        hlayout.addWidget(self.capturePosX)
        hlayout.addWidget(self.capturePosY)
        hlayout.addWidget(self.captureWidth)
        hlayout.addWidget(self.captureHeight)
        layout.addLayout(hlayout)

        #---------------------------------------
        # (hwnd, window_name)
        window_names = WindowCapture.list_window_names()
        #self.dbg['DEBUG'].tr(window_names)
        self.windowSelector = self.WindowSelectorComboBox(self)
        for name in window_names:
            if name[1]:
                self.windowSelector.addItems([name[1]])
        layout.addWidget(self.windowSelector)
        self.windowSelector.setCurrentIndex(0)

        #---------------------------------------
        self.captureButton = QPushButton("start")
        self.captureButton.clicked.connect(self.start)
        layout.addWidget(self.captureButton)

        self.setLayout(layout)

    def on_screen_capture(self, keyb_rgb):
        self.rgb_frame_signal.emit(keyb_rgb, (1.0,1.0,1.0))
        if keyb_rgb == None:
            self._stopped()

    def start(self, window_name=None):
        if self.windowCaptureThread and self.windowCaptureThread.isRunning():
            self.stop()
            return

        self.dbg['DEBUG'].tr("start win capture")

        try:
            window_name = self.windowSelector.currentText()
            window_off_size = (int(self.capturePosX.text()), int(self.capturePosY.text()), int(self.captureWidth.text()), int(self.captureHeight.text()))
            self.windowCaptureThread = self.WindowCaptureThread(window_name, window_off_size, self.rgb_matrix_size, 0.1)
            self.windowCaptureThread.connect_callback(self.on_screen_capture)
            self.windowCaptureThread.start()
        except Exception as e:
            self.dbg['DEBUG'].tr(f"error: {e}")
            self.stop()
        else:
            self.running = True
            self.captureButton.setText("stop")

    def _stopped(self):
        self.running = False
        self.dbg['DEBUG'].tr("win capture stopped")
        self.captureButton.setText("start")

    def stop(self):
        self.windowCaptureThread.stop()
        self.windowCaptureThread.wait()
        self.windowCaptureThread = None
        self._stopped()

    def closeEvent(self, event):
        if self.windowCaptureThread:
            self.stop()

#-------------------------------------------------------------------------------

class HexEditor(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setFont(QFont("Courier New", 9))
        self.setAcceptRichText(False)  # Only plain text to avoid formatting

    def keyPressEvent(self, event: QKeyEvent):
        if event.matches(QKeySequence.Paste):
            self.handlePaste()
            return

        # Allow undo
        if event.matches(QKeySequence.Undo):
            self.undo()
            return
        # Allow redo
        elif event.matches(QKeySequence.Redo):
            self.redo()
            return

        text = event.text()
        # Only allow hexadecimal characters
        if text.upper() in '0123456789ABCDEF':
            super().keyPressEvent(event)
            self.formatText()
        # Allow backspace and delete
        elif event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            super().keyPressEvent(event)
            self.formatText()
        # Ignore other keys
        else:
            event.ignore()

    def handlePaste(self):
            clipboard = QApplication.clipboard()
            text = clipboard.text()
            # Validate and clean the pasted text
            cleaned_text = ''.join(filter(lambda x: x.upper() in '0123456789ABCDEF', text.upper()))
            if cleaned_text:
                # Only insert cleaned text
                self.insertPlainText(cleaned_text)
                self.formatText()
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.setTextCursor(cursor)
            else:
                QMessageBox.warning(self, "Invalid Paste Content", "Pasted text contains non-hexadecimal characters.")


    def formatText(self):
        cursor_pos = self.textCursor().position()
        # Remove spaces and newlines for clean formatting
        text = self.toPlainText().replace(" ", "").replace("\n", "")
        # Insert space after every 2 hex characters and newline after every 32 characters
        formatted_text = ' '.join(text[i:i+2] for i in range(0, len(text), 2))
        formatted_text = '\n'.join(formatted_text[i:i+48] for i in range(0, len(formatted_text), 48))  # 32 hex chars + 16 spaces = 48
        self.setPlainText(formatted_text)
        cursor = self.textCursor()
        cursor.setPosition(cursor_pos)
        self.setTextCursor(cursor)

    def is_hex(self, s):
        try:
            int(s, 16)
            return True
        except ValueError:
            return False

    def getBinaryContent(self):
        # Remove spaces and newlines to get a clean hex string
        hex_str = self.toPlainText().replace(" ", "").replace("\n", "")
        try:
            # Convert hex string to a binary array (bytes object)
            data = bytes.fromhex(hex_str)
            return data
        except ValueError:
            # Handle the case where the hex string is invalid
            QMessageBox.warning(self, "Invalid Hex Content", "The content contains non-hexadecimal characters or an incomplete byte.")
            return None

class RGBDynLDAnimationTab(QWidget):
    signal_dynld_function = Signal(int, bytearray)

    def __init__(self):
        #-----------------------------------------------------------
        self.dbg = {}
        self.dbg['DEBUG']       = DebugTracer(print=1, trace=1)
        #-----------------------------------------------------------

        super().__init__()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.addStretch(1)

        #---------------------------------------
        # dynld animation bin file
        hLayout = QHBoxLayout()
        dynldBinLabel = QLabel("animation bin")
        self.dynldBinInput = QLineEdit("v:\shared\qmk\dynld_animation.bin")
        hLayout.addWidget(dynldBinLabel)
        hLayout.addWidget(self.dynldBinInput)
        self.loadButton = QPushButton("load")
        self.loadButton.clicked.connect(self.loadDynLDAnimationFunc)
        hLayout.addWidget(self.loadButton)
        layout.addLayout(hLayout)

        #---------------------------------------
        self.dynldFunTextEdit = HexEditor()
        self.loadDynLDAnimationFunc()

        layout.addWidget(self.dynldFunTextEdit)

        #---------------------------------------
        self.sendButton = QPushButton("send to keyboard")
        self.sendButton.clicked.connect(self.sendDynLDAnimationFunc)
        layout.addWidget(self.sendButton)

        self.setLayout(layout)

    def loadDynLDAnimationFunc(self):
        try:
            with open(self.dynldBinInput.text(), 'rb') as file:
                buf = bytearray(file.read())
                hexbuf = buf.hex(' ')
                self.dynldFunTextEdit.setText(hexbuf)
                self.dynldFunTextEdit.formatText()
        except Exception as e:
            self.dbg['DEBUG'].tr(f"error: {e}")

    def sendDynLDAnimationFunc(self):
        fundata = self.dynldFunTextEdit.getBinaryContent()
        if fundata:
            DYNLD_ANIMATION_FUNC = 0
            self.signal_dynld_function.emit(DYNLD_ANIMATION_FUNC, fundata)



#-------------------------------------------------------------------------------

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
        self.dbg = {}
        self.dbg['DEBUG'] = DebugTracer(print=1, trace=1, obj=self)

        self.currentLayer = 0
        self.num_keyb_layers = num_keyb_layers
        self.wsServer = None

        super().__init__()
        self.initUI()

    async def ws_handler(self, websocket, path):
        async for message in websocket:
            self.dbg['DEBUG'].tr(f"ws_handler: {message}")
            if message.startswith("layer:"):
                try:
                    layer = int(message.split(":")[1])
                    self.keyb_layer_set_signal.emit(layer)
                except Exception as e:
                    self.dbg['DEBUG'].tr(f"ws_handler: {e}")

    def wsServerStartStop(self, state):
        #self.dbg['DEBUG'].tr(f"{state}")
        if Qt.CheckState(state) == Qt.CheckState.Checked:
            self.dbg['DEBUG'].tr("ws server start")
            self.wsServer = WSServer(self.ws_handler, int(self.layerSwitchServerPort.text()))
            self.wsServer.start()
        else:
            try:
                self.wsServer.stop()
                self.wsServer.wait()
                self.wsServer = None
            except Exception as e:
                self.dbg['DEBUG'].tr(f"{e}")

    async def ws_handler(self, websocket, path):
        async for message in websocket:
            self.dbg['DEBUG'].tr(f"ws_handler: {message}")
            if message.startswith("layer:"):
                try:
                    layer = int(message.split(":")[1])
                    self.keyb_layer_set_signal.emit(layer)
                except Exception as e:
                    self.dbg['DEBUG'].tr(f"ws_handler: {e}")

    def wsServerStartStop(self, state):
        #self.dbg['DEBUG'].tr(f"{state}")
        if Qt.CheckState(state) == Qt.CheckState.Checked:
            self.dbg['DEBUG'].tr("ws server start")
            self.wsServer = WSServer(self.ws_handler, int(self.wsServerPort.text()))
            self.wsServer.start()
        else:
            try:
                self.wsServer.stop()
                self.wsServer.wait()
                self.wsServer = None
            except Exception as e:
                self.dbg['DEBUG'].tr(f"{e}")

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
        #---------------------------------------
        # instruction summary
        self.label = QLabel("select default layer above, the foreground application is traced here below.\n"
                            "select program(s) and the layer to use in the dropdown box below.\n"
                            "select '-' to unselect program.\n"
                            "\n"
                            "enabling \"layer switch ws server\" allow applications to send layer switch requests\n"
                            "by sending \"layer:<number>\" to \"ws://localhost:<port>\"\n"
                            )
        layout.addWidget(self.label)
        #---------------------------------------
        # "layer switch ws server" enable checkbox plus port input
        self.layerSwitchServerCheckbox = QCheckBox("enable ws server", self)
        self.layerSwitchServerPort = QLineEdit("8765")
        port_validator = QIntValidator(0, 65535, self)
        self.layerSwitchServerPort.setValidator(port_validator)
        self.layerSwitchServerPort.setFixedWidth(50)
        self.layerSwitchServerCheckbox.stateChanged.connect(self.wsServerStartStop)
        hlayout = QHBoxLayout()
        hlayout.addStretch(1)
        hlayout.addWidget(self.layerSwitchServerCheckbox)
        hlayout.addWidget(self.layerSwitchServerPort)
        layout.addLayout(hlayout)

        #---------------------------------------
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
            layout.addWidget(self.programSelector[i])

            self.layerSelector.append(QComboBox())
            self.layerSelector[i].addItems([str(i) for i in range(self.num_keyb_layers)])
            self.layerSelector[i].setCurrentIndex(0)
            layout.addWidget(self.layerSelector[i])

        #---------------------------------------
        self.setLayout(layout)

        # Connect winfocusTextEdit mouse press event
        self.winfocusTextEdit.mousePressEvent = self.selectLine


    def on_default_layer_changed(self, layer):
        self.dbg['DEBUG'].tr(f"default layer changed to {layer}")
        self.defLayerSelector.setCurrentIndex(layer)


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


    def closeEvent(self, event):
        if self.wsServer:
            self.wsServer.stop()
            self.wsServer.wait()

#-------------------------------------------------------------------------------

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
        self.load_text_file("animation.py")

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
        self.dbg = {}
        self.dbg['DEBUG']   = DebugTracer(print=1, trace=1)

        self.rgb_matrix_size = rgb_matrix_size
        super().__init__()
        self.initUI()

    def initUI(self):
        dbg = self.dbg['DEBUG']
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

        w_inch = 4
        h_inch = self.rgb_matrix_size[1] / self.rgb_matrix_size[0] * w_inch
        self.figure.set_size_inches((w_inch, h_inch))
        self.figure.set_dpi(100)
        if dbg.print:
            width, height = self.figure.get_size_inches() * self.figure.get_dpi()
            dbg.tr(f"canvas size: {width}x{height}")

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
                self.startButton.setText("stop")
        else:
            self.ani.event_source.stop()
            self.ani = None
            self.rgb_frame_signal.emit(None, (0,0,0))
            self.startButton.setText("start")


    def captureAnimationFrame(self):
        if self.ani == None:
            return

        self.ani.pause()

        self.canvas.draw()
        buffer = np.frombuffer(self.canvas.buffer_rgba(), dtype=np.uint8)
        width, height = self.figure.get_size_inches() * self.figure.get_dpi()
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

        QTimer.singleShot(0, self.captureAnimationFrame)
        return ret

    def closeEvent(self, event):
        if self.ani:
            self.ani.event_source.stop()
            self.ani = None

#-------------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, keyboard_vid_pid):
        self.keyboard_vid_pid = keyboard_vid_pid
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('QMK Firmata')
        self.setGeometry(100, 100, app_width, app_height)
        self.setFixedSize(app_width, app_height)

        # instantiate firmata keyboard
        self.keyboard = FirmataKeyboard(port=None, vid_pid=self.keyboard_vid_pid)
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
        # connect signals
        self.keyboard.signal_console_output.connect(self.console_tab.update_text)
        self.keyboard.signal_debug_mask.connect(self.console_tab.update_debug_mask)
        self.keyboard.signal_macwin_mode.connect(self.console_tab.update_macwin_mode)
        self.keyboard.signal_default_layer.connect(self.layer_switch_tab.on_default_layer_changed)
        self.keyboard.signal_rgb_matrix_mode.connect(self.rgb_matrix_tab.update_rgb_matrix_mode)

        self.console_tab.signal_dbg_mask.connect(self.keyboard.keyb_dbg_mask_set)
        self.console_tab.signal_macwin_mode.connect(self.keyboard.keyb_macwin_mode_set)
        self.console_tab.signal_dynld_function.connect(self.keyboard.keyb_dynld_function_set)

        self.rgb_matrix_tab.signal_rgb_matrix_mode.connect(self.keyboard.keyb_rgb_matrix_mode_set)
        self.rgb_matrix_tab.rgb_video_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.rgb_matrix_tab.rgb_animation_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.rgb_matrix_tab.rgb_audio_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.rgb_matrix_tab.rgb_capture_tab.rgb_frame_signal.connect(self.keyboard.keyb_rgb_buf_set)
        self.rgb_matrix_tab.rgb_dynld_animation_tab.signal_dynld_function.connect(self.keyboard.keyb_dynld_function_set)

        self.layer_switch_tab.keyb_layer_set_signal.connect(self.keyboard.keyb_default_layer_set)

        #-----------------------------------------------------------
        # window focus listener
        self.winfocus_listener = WinFocusListener()
        self.winfocus_listener.winfocus_signal.connect(self.layer_switch_tab.on_winfocus)
        self.winfocus_listener.start()

        #-----------------------------------------------------------
        # start keyboard communication
        self.keyboard.start()

    def closeEvent(self, event):
        self.winfocus_listener.stop()
        self.keyboard.stop()
        # close event to child widgets
        for child in self.findChildren(QWidget):
            child.closeEvent(event)
        event.accept()


class KeyboardSelectionPopup(QMessageBox):
    def __init__(self, keyboards):
        super().__init__()
        self.setWindowTitle('select keyboard')
        self.setText('keyboard:')

        # dropdown (combo box) for keyboard selection
        self.comboBox = QComboBox()
        self.comboBox.addItems(keyboards)

        # Add the combo box to the QMessageBox layout
        layout = self.layout()
        layout.addWidget(self.comboBox, 1, 1, 1, layout.columnCount())

        # Add an OK button
        self.addButton(QMessageBox.Ok)

        # Connect the OK button click to a handler (this example uses lambda for simplicity)
        self.buttonClicked.connect(lambda: self.accept())

    def selected_keyboard(self):
        return self.comboBox.currentText()


def detect_keyboards():
    hid_devices = hid.enumerate()
    def device_attached(vendor_id, product_id):
        for device in hid_devices:
            if device['vendor_id'] == vendor_id and device['product_id'] == product_id:
                return True
        return False

    keyboard_models = FirmataKeyboard.loadKeyboardModels()
    keyboards = []
    print (f"keyboards: {keyboard_models[0]}")
    for model in keyboard_models[0].values():
        if device_attached(model.VID, model.PID):
            print (f"keyboard found: {model.NAME} ({hex(model.VID)}:{hex(model.PID)})")
            keyboards.append(model.NAME)

    return keyboards, keyboard_models[0]


def main(keyboard_vid_pid):
    from PySide6.QtCore import QLocale
    locale = QLocale("C")
    QLocale.setDefault(locale)
    app = QApplication(sys.argv)

    selected_keyboard = ""
    if keyboard_vid_pid[0] == None:
        keyboards, keyb_models = detect_keyboards()
        if len(keyboards):
            selection_popup = KeyboardSelectionPopup(keyboards)
            if selection_popup.exec():
                selected_keyboard = selection_popup.selected_keyboard()
                keyboard_vid_pid = keyb_models[selected_keyboard].VID, keyb_models[selected_keyboard].PID

    main_window = MainWindow(keyboard_vid_pid)
    main_window.show()
    sys.exit(app.exec())

#-------------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="keyboard vendor/product id")
    parser.add_argument('--vid', required=False, type=lambda x: int(x, 16),
                        help='keyboard vid in hex')
    parser.add_argument('--pid', required=False, type=lambda x: int(x, 16),
                        help='keyboard pid in hex')
    args = parser.parse_args()

    main((args.vid, args.pid))
