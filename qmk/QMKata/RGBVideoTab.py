import cv2, numpy as np, time
import asyncio, websockets

from PySide6 import QtCore
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QSlider, QHBoxLayout, QLineEdit, QCheckBox
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap, QColor, QIntValidator

from WSServer import WSServer
from DebugTracer import DebugTracer

class RGBVideoTab(QWidget):
    signal_rgb_image = Signal(QImage, object)

    def __init__(self, size, rgb_matrix_tab, rgb_matrix_size):
        self.dbg = DebugTracer(zones={'D':0, 'WS_MSG':0}, obj=self)
        super().__init__()

        self.size_w, self.size_h = size
        self.rgb_matrix_tab = rgb_matrix_tab
        self.cap = None
        self.framerate = 25
        self.rgb_matrix_size = rgb_matrix_size
        self.rgb_multiplier = (1.0,1.0,1.0)
        self.init_gui()

    async def ws_handler(self, websocket, path):
        try:
            async for message in websocket:
                try:
                    message = bytearray(message, 'utf-8')
                except:
                    pass # already bytearray
                self.dbg.tr('WS_MSG', "ws_handler: {}", message)
                sub = b"rgb."
                if message.startswith(sub):
                    message = message[len(sub):]
                    subs = [ b"mode:", b"img:" ]
                    for sub in subs:
                        if message.startswith(sub):
                            if sub == b"img:":
                                data = message[len(sub):]
                                w = self.rgb_matrix_size[0]
                                h = self.rgb_matrix_size[1]
                                img = QImage(w, h, QImage.Format_RGB888)
                                img.fill(QColor('black'))
                                for y in range(h):
                                    for x in range(w):
                                        index = (y * w + x) * 3
                                        try:
                                            r, g, b = data[index], data[index + 1], data[index + 2]
                                            img.setPixelColor(x, y, QColor(r, g, b))
                                        except Exception as e:
                                            #self.dbg.tr('WS_MSG', "ws_handler: {}" ,e)
                                            pass

                                self.signal_rgb_image.emit(img, self.rgb_multiplier)
                                #self.dbg.tr('WS_MSG', "ws_handler:emit(img) done")
                self.dbg.tr('WS_MSG', "ws_handler: message handled")
                await asyncio.sleep(0)  # Ensures control is yielded back to the event loop

        except Exception as e:
            self.dbg.tr('WS_MSG', "ws_handler: {}", e)
        self.dbg.tr('WS_MSG', "ws_handler: done")
        self.signal_rgb_image.emit(None, self.rgb_multiplier)

    def ws_server_startstop(self, state):
        #self.dbg.tr('D', "state:{}", state)
        if Qt.CheckState(state) == Qt.CheckState.Checked:
            self.ws_server = WSServer(self.ws_handler, int(self.ws_server_port.text()))
            self.ws_server.start()
        else:
            try:
                self.ws_server.stop()
                self.ws_server.wait()
                self.ws_server = None
            except Exception as e:
                self.dbg.tr('D', "{}", e)

    def init_gui(self):
        layout = QVBoxLayout()
        self.video_label = QLabel("")
        self.video_label.setFixedSize(self.size_w, self.size_h)
        self.video_label.setAlignment(Qt.AlignTop)

        hlayout = QHBoxLayout()
        self.open_button = QPushButton("open file")
        self.open_button.setFixedWidth(100)
        self.open_button.clicked.connect(self.open_file)
        #---------------------------------------
        #region "rgb video ws server" enable checkbox plus port input
        self.ws_server_checkbox = QCheckBox("enable ws server", self)
        self.ws_server_port = QLineEdit("8787")
        port_validator = QIntValidator(0, 65535, self)
        self.ws_server_port.setValidator(port_validator)
        self.ws_server_port.setFixedWidth(50)
        self.ws_server_checkbox.stateChanged.connect(self.ws_server_startstop)
        hlayout = QHBoxLayout()
        hlayout.addStretch(1)
        hlayout.addWidget(self.ws_server_checkbox)
        hlayout.addWidget(self.ws_server_port)
        #endregion

        controls_layout = QHBoxLayout()
        self.framerate_label = QLabel("frame rate")
        self.framerate_slider = QSlider(Qt.Horizontal)
        self.framerate_slider.setMinimum(1)  # Minimum framerate
        self.framerate_slider.setMaximum(120)  # Maximum framerate
        self.framerate_slider.setValue(self.framerate)  # Set the default value
        self.framerate_slider.setTickInterval(1)  # Set tick interval
        self.framerate_slider.setTickPosition(QSlider.TicksBelow)
        self.framerate_slider.setToolTip("frame rate")
        self.framerate_slider.valueChanged.connect(self.adjust_framerate)

        #region framerate/RGB multiplier sliders
        rgb_multiply_layout = QHBoxLayout()
        self.rgb_r_label = QLabel("r")
        self.rgb_r_slider = QSlider(QtCore.Qt.Horizontal)
        self.rgb_r_slider.setMinimum(0)
        self.rgb_r_slider.setMaximum(300)
        self.rgb_r_slider.setValue(int(self.rgb_multiplier[0]*100))
        self.rgb_r_slider.setTickInterval(10)
        self.rgb_r_slider.setTickPosition(QSlider.TicksBelow)
        self.rgb_r_slider.setToolTip("red multiplier")
        self.rgb_r_slider.valueChanged.connect(self.adjust_rgb_multiplier)
        self.rgb_g_label = QLabel("g")
        self.rgb_g_slider = QSlider(Qt.Horizontal)
        self.rgb_g_slider.setMinimum(0)
        self.rgb_g_slider.setMaximum(300)
        self.rgb_g_slider.setValue(int(self.rgb_multiplier[1]*100))
        self.rgb_g_slider.setTickInterval(10)
        self.rgb_g_slider.setTickPosition(QSlider.TicksBelow)
        self.rgb_g_slider.setToolTip("green multiplier")
        self.rgb_g_slider.valueChanged.connect(self.adjust_rgb_multiplier)
        self.rgb_b_label = QLabel("b")
        self.rgb_b_slider = QSlider(Qt.Horizontal)
        self.rgb_b_slider.setMinimum(0)
        self.rgb_b_slider.setMaximum(300)
        self.rgb_b_slider.setValue(int(self.rgb_multiplier[2]*100))
        self.rgb_b_slider.setTickInterval(10)
        self.rgb_b_slider.setTickPosition(QSlider.TicksBelow)
        self.rgb_b_slider.setToolTip("blue multiplier")
        self.rgb_b_slider.valueChanged.connect(self.adjust_rgb_multiplier)

        controls_layout.addWidget(self.framerate_label)
        controls_layout.addWidget(self.framerate_slider)
        rgb_multiply_layout.addWidget(self.rgb_r_label)
        rgb_multiply_layout.addWidget(self.rgb_r_slider)
        rgb_multiply_layout.addWidget(self.rgb_g_label)
        rgb_multiply_layout.addWidget(self.rgb_g_slider)
        rgb_multiply_layout.addWidget(self.rgb_b_label)
        rgb_multiply_layout.addWidget(self.rgb_b_slider)
        #endregion

        layout.addLayout(hlayout)
        layout.addWidget(self.video_label)
        layout.addWidget(self.open_button)
        layout.addLayout(controls_layout)
        layout.addLayout(rgb_multiply_layout)
        self.setLayout(layout)

    def timer_interval(self):
        try:
            process_time = self.process_time
        except:
            process_time = 10

        interval = 1000 / self.framerate - process_time
        return interval if interval > 0 else 1

    def adjust_framerate(self, value):
        self.framerate = value
        self._timer_interval = self.timer_interval()

    def adjust_rgb_multiplier(self, value):
        if self.sender() == self.rgb_r_slider:
            self.rgb_multiplier = (value/100, self.rgb_multiplier[1], self.rgb_multiplier[2])
        if self.sender() == self.rgb_g_slider:
            self.rgb_multiplier = (self.rgb_multiplier[0], value/100, self.rgb_multiplier[2])
        if self.sender() == self.rgb_b_slider:
            self.rgb_multiplier = (self.rgb_multiplier[0], self.rgb_multiplier[1], value/100)
        #print(self.RGB_multiplier)

    def open_file(self):
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None
            self.signal_rgb_image.emit(None, self.rgb_multiplier)
            self.open_button.setText("open file")
            return

        filename, _ = QFileDialog.getOpenFileName(self, "open file", "", "Video Files (*.mp4 *.avi *.mov *.webm *.gif)")
        if filename:
            self.cap = cv2.VideoCapture(filename)
            fps = self.cap.get(cv2.CAP_PROP_FPS)  # Get the video's frame rate
            self.framerate = fps if fps > 0 else 25
            self.framerate_slider.setValue(int(self.framerate))
            self.adjust_framerate(self.framerate)
            QTimer.singleShot(self.timer_interval(), self.display_video_frame)

            self.dbg.tr('D', "frame rate:{}", self.framerate)
            self.open_button.setText("stop")

    def display_video_frame(self):
        if not self.cap:
            return

        QTimer.singleShot(self._timer_interval, self.display_video_frame)
        #self.dbg.tr('D', "capture image:")
        #start = cv2.getTickCount()
        ret, frame = self.cap.read()
        if ret:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            rgb_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            scaled_img = rgb_img.scaled(self.size_w, self.size_h, aspectMode=QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            self.video_label.setPixmap(QPixmap.fromImage(scaled_img))

            keyb_rgb = scaled_img.scaled(self.rgb_matrix_size[0], self.rgb_matrix_size[1])
            self.signal_rgb_image.emit(keyb_rgb, self.rgb_multiplier)
            #self.process_time = cv2.getTickCount() - start
            #self.dbg.tr('D', "image emitted {}", self.process_time)
        else:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # restart

    def print_rgb_data(self, frame):
        print(frame[0,0])

    def closeEvent(self, event):
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()
