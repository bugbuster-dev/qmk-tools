import numpy as np
import time, json

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QFrame, QFileDialog
from PySide6.QtCore import Signal, QThread, QTimer
from PySide6.QtGui import QImage, QColor, QIntValidator, QDoubleValidator

from DebugTracer import DebugTracer
try:
    import pyaudiowpatch as pyaudio
except:
    print("pyaudiowpatch not installed")

#-------------------------------------------------------------------------------
class AudioCaptureThread(QThread):

    def __init__(self, freq_bands, interval):
        self.dbg = DebugTracer(zones={'D':0}, obj=self)

        super().__init__()
        self.running = False
        self.freq_bands = freq_bands
        self.interval = interval
        self.paudio = pyaudio.PyAudio()

    def connect_callback(self, callback):
        self.callback = callback

    def set_freq_bands(self, freq_bands):
        self.freq_bands = freq_bands

    def run(self):
        dbg_zone = 'DEBUG'

        self.paudio = pyaudio.PyAudio()
        default_speakers = None
        try:
            # see https://github.com/s0d3s/PyAudioWPatch/blob/master/examples/pawp_record_wasapi_loopback.py
            wasapi_info = self.paudio.get_host_api_info_by_type(pyaudio.paWASAPI)
            self.dbg.tr(dbg_zone, f"wasapi: {wasapi_info}")

            default_speakers = self.paudio.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
            if not default_speakers["isLoopbackDevice"]:
                for loopback in self.paudio.get_loopback_device_info_generator():
                    if default_speakers["name"] in loopback["name"]:
                        default_speakers = loopback
                        break

            self.dbg.tr(dbg_zone, f"loopback device: {default_speakers}")
        except Exception as e:
            self.dbg.tr(dbg_zone, f"wasapi not supported: {e}")
            return

        FORMAT = pyaudio.paFloat32
        CHANNELS = default_speakers["maxInputChannels"]
        RATE = int(default_speakers["defaultSampleRate"])
        INPUT_INDEX = default_speakers["index"]
        CHUNK = int(RATE * self.interval)

        self.running = True
        self.stream = self.paudio.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK,
                        input_device_index=INPUT_INDEX)
        self.dbg.tr(dbg_zone, f"audio stream {self.stream} opened")

        while self.running:
            frames = []
            try:
                data = self.stream.read(CHUNK)
                frames = np.frombuffer(data, dtype=np.float32)
            except Exception as e:
                self.dbg.tr(dbg_zone, f"audio stream read error: {e}")
                self.running = False
                break

            audio_data = np.hstack(frames)
            freq_data = np.fft.rfft(audio_data)
            freq_magnitude = np.abs(freq_data)

            # Calculate frequency bins
            freq_bins = np.fft.rfftfreq(len(audio_data), d=1./RATE)
            peak_levels = []
            for f_min, f_max in self.freq_bands:
                # Find the bin indices corresponding to the frequency range
                idx = np.where((freq_bins >= f_min) & (freq_bins <= f_max))
                if len(freq_magnitude[idx]) > 0:
                    peak_level = np.max(freq_magnitude[idx])
                    peak_levels.append(peak_level)

            self.callback(peak_levels)

        self.stream.stop_stream()
        self.stream.close()
        self.dbg.tr(dbg_zone, f"audio stream {self.stream} closed")
        self.paudio.terminate()
        self.callback(None)

    def stop(self):
        try:
            self.stream.stop_stream()
        except Exception as e:
            pass
        self.running = False

#-------------------------------------------------------------------------------
class RGBAudioTab(QWidget):
    signal_rgb_image = Signal(QImage, object)
    signal_peak_levels = Signal(object)

    @staticmethod
    def freq_bands_linear(f_min, f_max, k):
        bands = []
        step = (f_max - f_min)/k
        for i in range(k):
            bands.append((f_min + i*step, f_min + (i+1)*step))
        return bands

    @staticmethod
    def freq_bands_log(f_min, f_max, k):
        #f_min = 27.5  # Hz (frequency of A0)
        #f_max = 4186  # Hz (frequency of C8)
        #k = 16        # number of bands
        # Calculate the frequency boundaries for each of the 16 bands
        i = np.arange(k + 1)  # index array from 0 to k (inclusive)
        bounds = f_min * (f_max / f_min) ** (i / k)
        # Prepare the bands in a readable format
        bands = [(bounds[n], bounds[n + 1]) for n in range(k)]
        return bands

    @staticmethod
    def freq_bands_for(f_min, f_max, k):
        return RGBAudioTab.freq_bands_log(f_min, f_max, k)

    def __init__(self, rgb_matrix_size):
        #-----------------------------------------------------------
        self.dbg = DebugTracer(zones={'D':0, "FREQ_BAND":0, "PEAK_LEVEL":0, "MAX_PEAK":0}, obj=self)
        #-----------------------------------------------------------
        self.freq_bands = []
        super().__init__()
        self.init_gui()

        #-----------------------------------------------------------
        self.rgb_matrix_size = rgb_matrix_size
        self.keyb_rgb = QImage(self.rgb_matrix_size[0], self.rgb_matrix_size[1], QImage.Format_RGB888)
        self.keyb_rgb_mask = QImage(self.keyb_rgb.size(), QImage.Format_Grayscale8)
        self.keyb_rgb_mask_mode = 0
        self.rgb_multiplier = (1.0,1.0,1.0)

        self.sample_count = 0
        try:
            self.audio_thread = AudioCaptureThread(self.freq_bands, 0.04)
        except:
            self.audio_thread = None

    def load_freqbands_jsonfile(self):
        filename, _ = QFileDialog.getOpenFileName(self, "open file", "", "json (*.json)")
        self.load_freq_bands_colors(filename)
        # update freq bands rgb ui
        for i, (band, color) in enumerate(zip(self.freq_bands, self.freq_rgb)):
            self.dbg.tr('FREQ_BAND', f"settext:[{i}]{band} {color}")
            self.freqbands_input[i][0].blockSignals(True)
            self.freqbands_input[i][1].blockSignals(True)
            self.freqbands_input[i][0].setText(format(band[0], '.2f'))
            self.freqbands_input[i][1].setText(format(band[1], '.2f'))
            self.freqbands_input[i][0].blockSignals(False)
            self.freqbands_input[i][1].blockSignals(False)

            for j in range(3):
                self.freqbands_rgb_input[i][j].blockSignals(True)
                self.freqbands_rgb_input[i][j].setText(format(color[j], '.2f'))
                self.freqbands_rgb_input[i][j].blockSignals(False)

            self.minmax_level_input[i][0].blockSignals(True)
            self.minmax_level_input[i][1].blockSignals(True)
            self.minmax_level_input[i][0].setText(str(self.min_max_level[i][0]))
            self.minmax_level_input[i][1].setText(str(self.min_max_level[i][1]))
            self.minmax_level_input[i][0].blockSignals(False)
            self.minmax_level_input[i][1].blockSignals(False)

    def init_gui(self):
        layout = QVBoxLayout()
        #-----------------------------------------------------------
        hlayout = QHBoxLayout()
        label = QLabel("frequency band | rgb | min/max level (0 for auto)")
        self.loadbutton = QPushButton("load")
        self.loadbutton.clicked.connect(self.load_freqbands_jsonfile)

        hlayout.addWidget(label)
        hlayout.addWidget(self.loadbutton)
        hlayout.addStretch(1)

        label = QLabel("peak level")
        self.peak_level = QLineEdit()
        self.peak_level.setFixedWidth(80)
        self.peak_level.setReadOnly(True)
        hlayout.addWidget(label)
        hlayout.addWidget(self.peak_level)

        layout.addLayout(hlayout)
        #-----------------------------------------------------------
        # load freq bands colors and add widgets
        self.load_freq_bands_colors()
        self.freqbands_input = []
        self.freqbands_rgb_input = []
        self.minmax_level_input = []
        self.db_min = []
        self.max_level = [] # max level used for rgb intensity
        self.max_level_running = []  # max level updated every sample
        for i, (band, color) in enumerate(zip(self.freq_bands, self.freq_rgb)):
            self.dbg.tr('FREQ_BAND', f"{band} {color}")
            self.max_level.append(15)
            self.max_level_running.append(0)
            low = QLineEdit()
            high = QLineEdit()
            low.setFixedWidth(60)
            high.setFixedWidth(60)
            low.setValidator(QIntValidator(10,20000))
            high.setValidator(QIntValidator(10,20000))
            low.setText(format(band[0], '.2f'))
            high.setText(format(band[1], '.2f'))
            low.textChanged.connect(self.update_freq_bands)
            high.textChanged.connect(self.update_freq_bands)
            self.freqbands_input.append((low,high))
            self.freqbands_rgb_input.append((QLineEdit(),QLineEdit(),QLineEdit()))
            hlayout = QHBoxLayout()
            hlayout.addWidget(low)
            hlayout.addWidget(high)
            separator = QFrame()
            separator.setFrameShape(QFrame.VLine)
            hlayout.addWidget(separator)
            #-----------------------
            for j, rgb in enumerate(self.freqbands_rgb_input[-1]):
                rgb.setValidator(QDoubleValidator(0.0,5.0,2))
                rgb.setFixedWidth(40)
                rgb.setText(format(color[j], '.2f'))
                rgb.textChanged.connect(self.update_freq_rgb)
                hlayout.addWidget(rgb)
            separator = QFrame()
            separator.setFrameShape(QFrame.VLine)
            hlayout.addWidget(separator)
            #-----------------------
            min_level = QLineEdit()
            min_level.setValidator(QIntValidator(0,1000))
            min_level.setFixedWidth(50)
            min_level.setText(str(self.min_max_level[i][0]))
            min_level.textChanged.connect(self.update_min_max_level)
            max_level = QLineEdit()
            max_level.setValidator(QIntValidator(0,1000))
            max_level.setFixedWidth(50)
            max_level.setText(str(self.min_max_level[i][1]))
            max_level.textChanged.connect(self.update_min_max_level)
            hlayout.addWidget(min_level)
            hlayout.addWidget(max_level)
            self.minmax_level_input.append((min_level, max_level))
            self.db_min.append(-27)

            hlayout.addStretch(1)
            layout.addLayout(hlayout)
        layout.addStretch(1)

        #-------------------------------------------------------------------------------
        self.start_button = QPushButton("start")
        self.start_button.clicked.connect(self.start)
        layout.addWidget(self.start_button)
        self.setLayout(layout)

    def load_freq_bands_colors(self, file_name='freq_bands_colors.json'):
        try:
            with open(file_name, 'r') as file:
                freq_bands_colors = json.load(file)
                self.freq_bands = freq_bands_colors['freq_bands']
                self.freq_rgb = freq_bands_colors['colors']
                self.min_max_level = freq_bands_colors['min_max_level']
                if len(self.freq_bands) > 31:
                    raise Exception("too many freq bands")
                if len(self.freq_bands) != len(self.freq_rgb):
                    raise Exception("freq_bands and colors have different lengths")
                self.dbg.tr('FREQ_BAND', f"freq_bands:{self.freq_bands}")
                self.dbg.tr('FREQ_BAND', f"freq_rgb:{self.freq_rgb}")
                self.dbg.tr('FREQ_BAND', f"min_max_level:{self.min_max_level}")
                if self.min_max_level is None or len(self.min_max_level) != len(self.freq_bands):
                    self.min_max_level = [(0,0) for _ in range(len(self.freq_bands))]
        except Exception as e:
            self.dbg.tr('DEBUG', f"error loading file: {e}")
            self.freq_bands = []
            self.freq_rgb = []
            self.min_max_level = []

    def save_freq_bands_colors(self):
        freq_bands_colors = {
            'freq_bands': self.freq_bands,
            'colors': self.freq_rgb,
            'min_max_level':self.min_max_level
        }
        with open('freq_bands_colors.json', 'w') as file:
            json.dump(freq_bands_colors, file, indent=4)

    def update_freq_rgb(self):
        n_ranges = len(self.freq_bands)
        self.freq_rgb = []
        for i in range(n_ranges):
            self.freq_rgb.append([float(self.freqbands_rgb_input[i][0].text()), float(self.freqbands_rgb_input[i][1].text()), float(self.freqbands_rgb_input[i][2].text())])

        self.dbg.tr('FREQ_BAND', f"freq band colors {self.freq_rgb}")

    def update_freq_bands(self):
        n_ranges = len(self.freq_bands)
        for i in range(n_ranges):
            self.freq_bands[i] = (float(self.freqbands_input[i][0].text()), float(self.freqbands_input[i][1].text()))

        self.dbg.tr('FREQ_BAND', f"freq bands {self.freq_bands}")
        if self.audio_thread:
            self.audio_thread.set_freq_bands(self.freq_bands)

    def update_min_max_level(self):
        n_ranges = len(self.freq_bands)
        min_max_level = []
        for i in range(n_ranges):
            min_max_level.append((int(self.minmax_level_input[i][0].text()), int(self.minmax_level_input[i][1].text())))
        self.min_max_level = min_max_level

    #-------------------------------------------------------------------------------
    def db_to_255(self, dB_value, dB_min=-60, dB_max=0):
        # Normalize dB value from [dB_min, dB_max] to [0, 1]
        normalized = (dB_value - dB_min) / (dB_max - dB_min)
        # Clip the normalized value to be within the range [0, 1]
        normalized = max(0, min(1, normalized))
        # Convert normalized value to an integer in the range [0, 255]
        mapped_value = int(round(255 * normalized))
        return mapped_value

    def peak_level_to_rgb(self, peak_levels, db_min, max_level, log_scale = True):
        r = g = b = 0
        MAX_RGB = 255
        for i in range(len(peak_levels)):
            try:
                peak_db = 20 * np.log10(peak_levels[i]/max_level[i])
                peak_db_rgb = self.db_to_255(peak_db, db_min[i], 0)
                #print(f"peak {i}: {peak_levels[i]} {peak_db} {peak_db_rgb}")
                if log_scale:
                    r += peak_db_rgb * self.freq_rgb[i][0]
                    g += peak_db_rgb * self.freq_rgb[i][1]
                    b += peak_db_rgb * self.freq_rgb[i][2]
                else:
                    r += peak_levels[i]/max_level[i] * self.freq_rgb[i][0] * MAX_RGB
                    g += peak_levels[i]/max_level[i] * self.freq_rgb[i][1] * MAX_RGB
                    b += peak_levels[i]/max_level[i] * self.freq_rgb[i][2] * MAX_RGB
            except Exception as e:
                self.dbg.tr('DEBUG', f"ppeak_level_to_rgb:{e}")
                pass # #bands updated in ui

        # rgb values are added for all bands, normalize with a factor
        r /= 6
        g /= 6
        b /= 6
        r = min(r, MAX_RGB)
        g = min(g, MAX_RGB)
        b = min(b, MAX_RGB)
        return r,g,b

    #-------------------------------------------------------------------------------
    def process_audiopeak_levels(self, peak_levels):
        if peak_levels is None:
            self.signal_rgb_image.emit(None, self.rgb_multiplier)
            return

        self.signal_peak_levels.emit(peak_levels)

        self.sample_count += 1
        if self.dbg.enabled('PEAK_LEVEL'):
            self.dbg.tr('PEAK_LEVEL', f"peak {self.sample_count}: {peak_levels}")

        # update "running max level", after N samples "max level" is adjusted with this
        peak_level = 0 # current sample peak level
        for i, lvl in enumerate(peak_levels):
            if lvl > self.max_level_running[i]:
                self.max_level_running[i] = lvl
            if lvl > peak_level:
                peak_level = lvl

        # update "max level" every N samples, brightness is based on current peak levels and "max level"
        if self.sample_count == 20:
            self.sample_count = 0
            max_level_running = 0
            max_level_running_band = 0
            for i in range(len(peak_levels)):
                try:
                    if self.max_level_running[i] > max_level_running:
                        max_level_running = self.max_level_running[i]
                        max_level_running_band = i

                    if self.min_max_level[i][0] == 0:
                        self.db_min[i] = -27
                    else: # user defined min level
                        self.db_min[i] = 20 * np.log10(self.min_max_level[i][0]/self.max_level[i])

                    if self.min_max_level[i][1] > 0: # user defined max level
                        self.max_level[i] = self.min_max_level[i][1]
                    else:
                        self.max_level[i] += (self.max_level_running[i] - self.max_level[i])/2
                except Exception as e:
                    self.dbg.tr('DEBUG', f"process_audiopeak_levels:{e}")
                    pass

            if self.dbg.enabled('MAX_PEAK'):
                try:
                    self.dbg.tr('MAX_PEAK', f"{time.monotonic()}:max level[{max_level_running_band}] {max_level_running}")
                except:
                    pass

            self.peak_level.setText(f"{max_level_running:.2f}")
            self.max_level_running = [0] * len(self.freq_bands)

        if all(level < 0.05 for (level) in peak_levels):
            # no audio
            return

        r,g,b = self.peak_level_to_rgb(peak_levels, self.db_min, self.max_level)
        self.keyb_rgb.fill(QColor(r,g,b))
        #-----------------------------------------------------------
        if self.running:
            #self.dbg.tr('DEBUG', f"send rgb {self.keyb_rgb}")
            self.signal_rgb_image.emit(self.keyb_rgb, self.rgb_multiplier)

    # todo: add effects
    # - mask leds per freq band/peak level
    # - trigger wave animation on freq band/peak level
    # - ...
    def apply_effect(self, img, peak_level):
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
                    # lines 1,2
                    mask_bits[1 * bytes_per_line + x] = 255
                    mask_bits[2 * bytes_per_line + x] = 255

            if self.keyb_rgb_mask_mode == 2:
                for x in range(x_range[0], x_range[1]):
                    # all lines
                    for i in range(img.height()):
                        mask_bits[i * bytes_per_line + x] = 255

            img.setAlphaChannel(self.keyb_rgb_mask)
            img = img.convertedTo(QImage.Format_RGB888)
            self.keyb_rgb = img

    def start(self):
        if not self.audio_thread:
            return

        if not self.audio_thread.isRunning():
            self.update_freq_rgb()
            self.update_freq_bands()
            self.update_min_max_level()
            self.audio_thread.connect_callback(self.process_audiopeak_levels)
            self.audio_thread.start()
            self.start_button.setText("stop")
            self.running = True
        else:
            self.audio_thread.stop()
            self.audio_thread.wait()
            self.start_button.setText("start")
            self.running = False

    def closeEvent(self, event):
        if not self.audio_thread:
            return

        if self.audio_thread.isRunning():
            self.audio_thread.stop()
            self.audio_thread.wait()
