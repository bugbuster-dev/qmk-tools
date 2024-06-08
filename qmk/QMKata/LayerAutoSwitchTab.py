from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QCheckBox, QHBoxLayout, QLineEdit, QTextEdit, QStyledItemDelegate
from PySide6.QtGui import QFont, QFontMetrics, QIntValidator, QMouseEvent
from PySide6.QtCore import Qt, Signal

from DebugTracer import DebugTracer
from WSServer import WSServer

#-------------------------------------------------------------------------------
class ProgramSelectorComboBox(QComboBox):
    class TabDelegate(QStyledItemDelegate):
        def paint(self, painter, option, index):
            text = index.data().replace("\t", " ")
            painter.drawText(option.rect, text)

    def __init__(self, winfocusText=None):
        super().__init__(None)
        self.winfocusText = winfocusText
        self.setItemDelegate(self.TabDelegate())

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)

        if event.button() == Qt.LeftButton:
            if self.winfocusText:
                self.clear()
                lines = self.winfocusText.toPlainText().split('\n')
                for line in lines:
                    self.addItem(line.strip())
                self.addItem("-")
                #print(self.winfocusText.toPlainText())

#-------------------------------------------------------------------------------
class LayerAutoSwitchTab(QWidget):
    signal_keyb_set_layer = Signal(int)
    num_program_selectors = 4

    def __init__(self, num_keyb_layers=8):
        self.dbg = DebugTracer(zones={'D':0}, obj=self)

        self.current_layer = 0
        self.num_keyb_layers = num_keyb_layers
        self.ws_server = None

        super().__init__()
        self.init_gui()

    async def ws_handler(self, websocket, path):
        async for message in websocket:
            self.dbg.tr('DEBUG', f"ws_handler: {message}")
            if message.startswith("layer:"):
                try:
                    layer = int(message.split(":")[1])
                    self.signal_keyb_set_layer.emit(layer)
                except Exception as e:
                    self.dbg.tr('DEBUG', f"ws_handler: {e}")

    def ws_server_startstop(self, state):
        #self.dbg.tr('DEBUG', f"{state}")
        if Qt.CheckState(state) == Qt.CheckState.Checked:
            self.ws_server = WSServer(self.ws_handler, int(self.layer_switch_server_port.text()))
            self.ws_server.start()
        else:
            try:
                self.ws_server.stop()
                self.ws_server.wait()
                self.ws_server = None
            except Exception as e:
                self.dbg.tr('DEBUG', f"{e}")

    async def ws_handler(self, websocket, path):
        async for message in websocket:
            self.dbg.tr('DEBUG', f"ws_handler: {message}")
            if message.startswith("layer:"):
                try:
                    layer = int(message.split(":")[1])
                    self.signal_keyb_set_layer.emit(layer)
                except Exception as e:
                    self.dbg.tr('DEBUG', f"ws_handler: {e}")

    def init_gui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)

        #---------------------------------------
        # default layer
        self.deflayer_label = QLabel("default layer")
        metrics = QFontMetrics(self.deflayer_label.font())
        self.deflayer_label.setFixedHeight(metrics.height())

        layout.addWidget(self.deflayer_label)
        # QComboBox for selecting layer
        self.deflayer_selector = QComboBox()
        self.deflayer_selector.addItems([str(i) for i in range(self.num_keyb_layers)])
        layout.addWidget(self.deflayer_selector)
        self.deflayer_selector.setCurrentIndex(0)
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
        self.layer_switch_server_checkbox = QCheckBox("enable ws server", self)
        self.layer_switch_server_port = QLineEdit("8765")
        port_validator = QIntValidator(0, 65535, self)
        self.layer_switch_server_port.setValidator(port_validator)
        self.layer_switch_server_port.setFixedWidth(50)
        self.layer_switch_server_checkbox.stateChanged.connect(self.ws_server_startstop)
        hlayout = QHBoxLayout()
        hlayout.addStretch(1)
        hlayout.addWidget(self.layer_switch_server_checkbox)
        hlayout.addWidget(self.layer_switch_server_port)
        layout.addLayout(hlayout)

        #---------------------------------------
        # for displaying processes which got foreground focus
        self.winfocus_textedit = QTextEdit()
        self.winfocus_textedit.setReadOnly(True)
        self.winfocus_textedit.setMaximumHeight(180)  # Adjust the height
        self.winfocus_textedit.textChanged.connect(self.limit_lines)
        layout.addWidget(self.winfocus_textedit)

        #---------------------------------------
        self.program_selector = []
        self.layer_selector = []
        for i in range(self.num_program_selectors):
            self.program_selector.append(ProgramSelectorComboBox(self.winfocus_textedit))
            self.program_selector[i].addItems(["" for i in range(5)])
            self.program_selector[i].setCurrentIndex(0)
            layout.addWidget(self.program_selector[i])

            self.layer_selector.append(QComboBox())
            self.layer_selector[i].addItems([str(i) for i in range(self.num_keyb_layers)])
            self.layer_selector[i].setCurrentIndex(0)
            layout.addWidget(self.layer_selector[i])
        #---------------------------------------
        self.setLayout(layout)

    def update_default_layer(self, layer):
        self.dbg.tr('DEBUG', f"default layer update: {layer}")
        self.deflayer_selector.setCurrentIndex(layer)

    def on_winfocus(self, line):
        self.update_winfocus_text(line)
        self.current_focus = line
        # foreground focus window info
        focus_win = line.split("\t")
        #self.dbg.tr('DEBUG', f"on_winfocus {focus_win}")
        for i, ps in enumerate(self.program_selector):
            compare_win = self.program_selector[i].currentText().split("\t")
            #self.dbg.tr('DEBUG', f"on_winfocus compare: {compare_win}")
            if focus_win[0].strip() == compare_win[0].strip() and \
               focus_win[1].strip() == compare_win[1].strip():
                layer = int(self.layer_selector[i].currentText())
                self.signal_keyb_set_layer.emit(layer)
                self.current_layer = layer
                self.dbg.tr('DEBUG', f"layer set: {layer}")
                return

        defaultLayer = self.deflayer_selector.currentIndex()
        if self.current_layer != defaultLayer:
            self.signal_keyb_set_layer.emit(defaultLayer)
            self.current_layer = defaultLayer
            self.dbg.tr('DEBUG', f"layer set: {defaultLayer}")

    def update_winfocus_text(self, line):
        self.winfocus_textedit.append(line)

    def limit_lines(self):
        lines = self.winfocus_textedit.toPlainText().split('\n')
        if len(lines) > 10:
            self.winfocus_textedit.setPlainText('\n'.join(lines[-10:]))

    def closeEvent(self, event):
        if self.ws_server:
            self.ws_server.stop()
            self.ws_server.wait()
