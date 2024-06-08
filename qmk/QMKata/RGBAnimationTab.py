import numpy as np, random
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTextEdit
from PySide6.QtGui import QFont, QImage, QKeyEvent
from PySide6.QtCore import Qt, QTimer, Signal

from DebugTracer import DebugTracer

def add_method_to_class(class_def, method):
    method_definition = method
    # Execute the method definition and retrieve the method from the local scope
    local_scope = {}
    exec(method_definition, globals(), local_scope)
    for method in list(local_scope.values()):
        #print(f"{method.__name__} added to class {class_def.__name__}")
        # Add the method to the class
        setattr(class_def, method.__name__, method)

#-------------------------------------------------------------------------------
class CodeTextEdit(QTextEdit):
    def __init__(self, filepath=None, parent=None):
        super().__init__(parent)
        self.setFont(QFont("Courier New", 9))
        if filepath:
            self.load_text_file(filepath)

    def insertFromMimeData(self, source):
        if source.hasText():
            # only plain text
            plain_text = source.text()
            self.insertPlainText(plain_text)
        else:
            super().insertFromMimeData(source)

    def load_text_file(self, filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as file:
                content = file.read()
                self.setPlainText(content)
        except Exception as e:
            print(f"Error opening {filepath}: {e}")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Tab:
            # four spaces instead of a tab
            self.insertPlainText("    ")
        else:
            super().keyPressEvent(event)

#-------------------------------------------------------------------------------
class RGBAnimationTab(QWidget):
    signal_rgb_image = Signal(QImage, object)

    def __init__(self, rgb_matrix_size):
        self.dbg = DebugTracer(zones={'D': 0}, obj=self)
        self.rgb_matrix_size = rgb_matrix_size
        super().__init__()
        self.init_gui()

    def init_gui(self):
        DPI = 100
        width = 800
        height = int((self.rgb_matrix_size[1]/self.rgb_matrix_size[0]) * width)
        w_inch = width/DPI
        h_inch = height/DPI

        # matplotlib figure for plotting
        self.figure = Figure(facecolor='black')
        self.figure.set_size_inches((w_inch, h_inch))
        self.figure.set_dpi(DPI)
        self.figure.subplots_adjust(left=0, right=1, top=1, bottom=0)

        self.ax = self.figure.add_subplot(111) # 1 1x1 subplot
        self.ax.set_facecolor('black')
        plt.axes().set_aspect('equal', 'datalim')
        # todo: aspect ratio

        if self.dbg.enabled('D'):
            _w, _h = self.figure.get_size_inches() * self.figure.get_dpi()
            self.dbg.tr('D', f"figure size:{_w}x{_h} dpi:{self.figure.get_dpi()}")

        #-------------------------------------------------------
        # text editor
        self.code_editor = CodeTextEdit("animation.py")
        # start animation button
        self.start_button = QPushButton("start")
        self.start_button.clicked.connect(self.start_animation)
        # canvas
        self.canvas = FigureCanvas(self.figure)
        #-------------------------------------------------------
        # add widgets to layout
        layout = QVBoxLayout()
        layout.addWidget(self.code_editor)
        layout.addWidget(self.canvas)
        layout.addWidget(self.start_button)
        self.setLayout(layout)

        # func animation parameters
        self.n_frames = 1000
        self.interval = 40
        self.ani = None

        self._audio_peak_levels = None

    def on_keypress(self, keypress_event):
        print("on_keypress: {} todo", keypress_event)

    def on_audio_peak_levels(self, peak_levels):
        self._audio_peak_levels = peak_levels

    def audio_peak_levels(self):
        return self._audio_peak_levels

    def start_animation(self):
        if self.ani is None:  # Prevent multiple instances if already running
            add_method_to_class(RGBAnimationTab, self.code_editor.toPlainText())
            try:
                init_fn_name, animate_fn_name = self.animate_methods()
                animate_init_method = getattr(RGBAnimationTab, init_fn_name)
                animate_method = getattr(RGBAnimationTab, animate_fn_name)
                setattr(RGBAnimationTab, "_animate_init", animate_init_method)
                setattr(RGBAnimationTab, "_animate", animate_method)
                self._animate_init()
                self.ani = animation.FuncAnimation(self.figure, self.animate, frames=self.n_frames, #init_func=self.init,
                                                blit=True, interval=self.interval, repeat=True)
            except Exception as e:
                print(e)

            if self.ani:
                self.start_button.setText("stop")
        else:
            self.ani.event_source.stop()
            self.ani = None
            self.signal_rgb_image.emit(None, (0,0,0))
            self.start_button.setText("start")

    def capture_animation_frame(self):
        if self.ani == None:
            return

        self.ani.pause()
        try:
            # capture the current frame from the canvas
            rgba_buffer = np.frombuffer(self.figure.canvas.buffer_rgba(), dtype=np.uint8)
            width, height = self.figure.get_size_inches() * self.figure.get_dpi()
            #if rgba_buffer.nbytes != width * height * 4:
                #self.dbg.tr('D', f"buffer size mismatch: {rgba_buffer.nbytes} != {width}x{height}x4")
            rgba_array = rgba_buffer.reshape(int(height), int(width), 4, order='C')
            rgba_qimg = QImage(rgba_array.data, width, height, QImage.Format_RGBA8888)
            keyb_rgb = rgba_qimg.scaled(self.rgb_matrix_size[0], self.rgb_matrix_size[1], Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.FastTransformation)
            keyb_rgb = keyb_rgb.convertToFormat(QImage.Format_RGB888)
            self.signal_rgb_image.emit(keyb_rgb, (1.0,1.0,1.0))
        except Exception as e:
            self.dbg.tr('E', f"capture_animation_frame: {e}")

        self.ani.resume()

    def animate(self, i):
        ret = self._animate(i)
        if i == self.n_frames:
            self.figure.clear()

        QTimer.singleShot(0, self.capture_animation_frame)
        return ret

    def closeEvent(self, event):
        if self.ani:
            self.ani.event_source.stop()
            self.ani = None
