import os, sys, time, hid, argparse
import cv2, numpy as np

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtWidgets import QTextEdit, QPushButton,  QLabel, QLineEdit, QTreeView
from PySide6.QtWidgets import  QComboBox, QMessageBox
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtGui import QIntValidator, QDoubleValidator
from PySide6.QtGui import QStandardItemModel, QStandardItem

from DebugTracer import DebugTracer
try:
    from WinFocusListener import WinFocusListener
except:
    pass

from FirmataKeyboard import FirmataKeyboard
from ConsoleTab import ConsoleTab
from WSServer import WSServer
from RGBVideoTab import RGBVideoTab
from RGBAudioTab import RGBAudioTab
from RGBAnimationTab import RGBAnimationTab, CodeTextEdit
from RGBDynLDAnimationTab import RGBDynLDAnimationTab
from LayerAutoSwitchTab import LayerAutoSwitchTab

if __name__ != "__main__":
    exit()

#-------------------------------------------------------------------------------
class RGBMatrixTab(QWidget): # todo: move to separate file
    def __init__(self, keyboard_model):
        self.keyboard_model = keyboard_model
        try:
            self.keyboard_config = self.keyboard_model.keyb_config()
        except:
            self.keyboard_config = None
        self.rgb_matrix_size = keyboard_model.rgb_matrix_size()
        super().__init__()
        self.init_gui()

    def init_gui(self):
        layout = QVBoxLayout()
        self.tab_widget = QTabWidget()

        self.rgb_video_tab = RGBVideoTab((app_width, app_height), self, self.rgb_matrix_size)
        self.rgb_animation_tab = RGBAnimationTab(self.rgb_matrix_size)
        self.rgb_audio_tab = RGBAudioTab(self.rgb_matrix_size)
        self.rgb_dynld_animation_tab = RGBDynLDAnimationTab()

        self.tab_widget.addTab(self.rgb_video_tab, 'video')
        self.tab_widget.addTab(self.rgb_animation_tab, 'animation')
        self.tab_widget.addTab(self.rgb_audio_tab, 'audio')
        self.tab_widget.addTab(self.rgb_dynld_animation_tab, 'dynld animation')

        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

#-------------------------------------------------------------------------------
class TreeviewWidget(QWidget):

    def __init__(self, keyboard_model):
        self.keyboard_model = keyboard_model
        self.endian = 'little'
        try:
            if self.keyboard_model.MCU[2].startswith("be"):
                self.endian = 'big'
        except:
            pass
        super().__init__()

    def init_gui(self):
        if not hasattr(self, 'layout'):
            self.layout = QVBoxLayout()

        # default tree view
        model = QStandardItemModel()
        self.tree_view = QTreeView()
        self.tree_view.setModel(model)
        self.tree_view.setFixedHeight(800)
        self.layout.addWidget(self.tree_view)
        self.layout.addStretch(1)
        self.setLayout(self.layout)

    def update_view_model(self, view_model):
        self.dbg.tr('DEBUG', f"update_view_model: {view_model}")
        self.tree_view.setModel(view_model)
        if view_model:
            try:
                view_model.dataChanged.connect(self.update_keyb_data)
            except Exception as e:
                self.dbg.tr('DEBUG', f"update_view_model: {e}")

    def update_view(self, item_data): # update from firmata keyboard
        try:
            item_id = item_data[0]
        except Exception as e:
            self.dbg.tr('DEBUG', f"update_view: {e}, {item_data}")
            return
        field_values = item_data[1]
        model = self.tree_view.model()
        item = model.item(item_id-1, 0)
        self.dbg.tr('DEBUG', f"update_view: {item.text()} {item_data}")
        for i in range(item.rowCount()): # todo: row number may not match field id
            try:
                value_item = item.child(i, 3)
                type_item = item.child(i, 1)
                field_value = field_values[i+1]
                if type(field_value) == bytearray:
                    value_item.setFont(QFont("Courier New", 7)) # todo move this to update_view_model
                    #self.dbg.tr('DEBUG', f"update_view: {type_item.text()}")
                    hex_string = ''
                    if type_item.text().endswith("uint8"):
                        item_size = 1
                        items_per_line = 16
                        format_str = "%02x "
                    elif type_item.text().endswith("uint16"):
                        item_size = 2
                        items_per_line = 10
                        format_str = "%04x "
                    elif type_item.text().endswith("uint32"):
                        item_size = 4
                        items_per_line = 8
                        format_str = "%08x "
                    elif type_item.text().endswith("uint64"):
                        item_size = 8
                        items_per_line = 4
                        format_str = "%016x "

                    if item.text() == "keymap layout":
                        items_per_line = self.keyboard_model.matrix_size()[0]

                    for i in range(0, len(field_value), item_size):
                        val = int.from_bytes(field_value[i:i+item_size], self.endian)
                        hex_string += format_str % val
                        #hex_string += f"{val:02x} "
                        if i % (items_per_line*item_size) == (items_per_line*item_size) - item_size:
                            hex_string += '\n'

                    formatted_string = hex_string
                    field_value = formatted_string
                    #field_value = field_value.hex(' ')
                value_item.setText(f"{field_value}")
            except Exception as e:
                self.dbg.tr('DEBUG', f"update_view: {e}")

#-------------------------------------------------------------------------------
class KeybConfigTab(TreeviewWidget):
    signal_keyb_set_config = Signal(tuple)
    signal_keyb_get_config = Signal(int)
    signal_macwin_mode = Signal(str)

    def __init__(self, keyboard_model):
        self.dbg = DebugTracer(zones={'D':0}, obj=self)

        self.keyboard_model = keyboard_model
        super().__init__(keyboard_model)
        self.init_gui()

    def update_keyb_data(self, tl, br, roles):
        #self.dbg.tr('DEBUG', f"update_keyb_data: topleft:{tl}, roles:{roles}")
        update = False
        if roles:
            for role in roles:
                if role == Qt.EditRole:
                    update = True

        if update: # todo update only if changed via ui not from update_view
            try:
                item = self.tree_view.model().itemFromIndex(tl)
                config_item = item.parent()
                config_id = config_item.row() + 1

                field_values = {}
                for i in range(config_item.rowCount()):
                    field = config_item.child(i, 0)
                    value = config_item.child(i, 3)
                    #print(f"{field.text()} = {value.text()}")
                    if value.text() == "":
                        return
                    if not value.flags() & Qt.ItemIsEditable:
                        return
                    field_values[i+1] = value.text()
            except Exception as e:
                self.dbg.tr('DEBUG', f"update_keyb_config: {e}")
                return
            config = (config_id, field_values)
            self.dbg.tr('DEBUG', f"update_keyb_config:signal emit {config}")
            self.signal_keyb_set_config.emit(config)

    def update_keyb_macwin_mode(self):
        macwin_mode = self.mac_win_mode_selector.currentText()
        self.signal_macwin_mode.emit(macwin_mode)

    def init_gui(self):
        hlayout = QHBoxLayout()
        config_label = QLabel("keyboard configuration")
        config_refresh_button = QPushButton("refresh")
        config_refresh_button.clicked.connect(lambda: self.signal_keyb_get_config.emit(0))
        hlayout.addWidget(config_label)
        hlayout.addWidget(config_refresh_button)
        hlayout.addStretch(1)
        #---------------------------------------
        # mac/win mode
        macwin_label = QLabel("mac/win mode")
        self.mac_win_mode_selector = QComboBox()
        self.mac_win_mode_selector.addItem('m')
        self.mac_win_mode_selector.addItem('w')
        self.mac_win_mode_selector.addItem('-')
        hlayout.addWidget(macwin_label)
        hlayout.addWidget(self.mac_win_mode_selector)
        self.mac_win_mode_selector.setCurrentIndex(1)
        self.mac_win_mode_selector.currentIndexChanged.connect(self.update_keyb_macwin_mode)
        self.mac_win_mode_selector.setFixedWidth(40)
        hlayout.addStretch(1)

        self.layout = QVBoxLayout()
        self.layout.addLayout(hlayout)
        super().init_gui()

    def update_macwin_mode(self, macwin_mode):
        self.mac_win_mode_selector.setCurrentIndex(0 if macwin_mode == 'm' else 1)

#-------------------------------------------------------------------------------
class KeybStatusTab(TreeviewWidget):
    signal_keyb_get_status = Signal(int, int)

    def __init__(self, keyboard_model):
        self.dbg = DebugTracer(zones={'D':0}, obj=self)

        self.keyboard_model = keyboard_model
        super().__init__(keyboard_model)
        self.init_gui()

    def init_gui(self):
        hlayout = QHBoxLayout()
        status_label = QLabel("keyboard status")
        status_refresh_button = QPushButton("refresh")
        every_label = QLabel("every (ms)")
        every_msec_edit = QLineEdit("100")
        every_msec_edit.setValidator(QIntValidator(0, 60000))
        every_msec_edit.setFixedWidth(50)
        status_refresh_button.clicked.connect(lambda: self.signal_keyb_get_status.emit(int(every_msec_edit.text()), 0))

        hlayout.addWidget(status_label)
        hlayout.addWidget(status_refresh_button)
        hlayout.addWidget(every_label)
        hlayout.addWidget(every_msec_edit)
        hlayout.addStretch(1)

        self.layout = QVBoxLayout()
        self.layout.addLayout(hlayout)
        super().init_gui()

#-------------------------------------------------------------------------------
class KeybScriptTab(QWidget):
    signal_run_script = Signal(str, object)
    signal_script_output = Signal(str)

    def __init__(self, keyboard_model):
        self.dbg = DebugTracer(zones={'D':0}, obj=self)
        #---------------------------------------
        self.keyboard_model = keyboard_model

        super().__init__()
        self.init_gui()
        self.signal_script_output.connect(self.append_script_output)

    def append_script_output(self, text):
        try:
            cursor = self.script_output.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.script_output.setTextCursor(cursor)
            self.script_output.insertPlainText(text)
            self.script_output.ensureCursorVisible()
        except:
            pass

    def exec_script(self):
        self.script_output.clear()
        script = self.code_editor.toPlainText()
        self.signal_run_script.emit(script, self.signal_script_output)

    def init_gui(self):
        layout = QVBoxLayout()

        self.exec_button = QPushButton("exec")
        self.exec_button.clicked.connect(self.exec_script)
        self.code_editor = CodeTextEdit()
        self.script_output = QTextEdit()
        self.script_output.setReadOnly(True)
        font = QFont()
        font.setFamily("Courier New")
        self.script_output.setFont(font)

        layout.addWidget(self.exec_button)
        layout.addWidget(self.code_editor)
        layout.addWidget(self.script_output)
        self.setLayout(layout)

#-------------------------------------------------------------------------------
app_width       = 800
app_height      = 900

class MainWindow(QMainWindow):
    def __init__(self, keyboard_vid_pid):
        self.keyboard_vid_pid = keyboard_vid_pid
        super().__init__()
        self.init_gui()

    def init_gui(self):
        self.setWindowTitle('QMK Firmata')
        self.setGeometry(100, 100, app_width, app_height)
        self.setFixedSize(app_width, app_height)

        # instantiate firmata keyboard
        self.keyboard = FirmataKeyboard(port=None, vid_pid=self.keyboard_vid_pid)
        num_keyb_layers = self.keyboard.num_layers()

        #-----------------------------------------------------------
        # add tabs
        tab_widget = QTabWidget()
        self.console_tab = ConsoleTab(self.keyboard.keyboardModel)
        self.rgb_matrix_tab = RGBMatrixTab(self.keyboard.keyboardModel)
        self.layer_switch_tab = LayerAutoSwitchTab(num_keyb_layers)
        self.keyb_config_tab = KeybConfigTab(self.keyboard.keyboardModel)
        self.keyb_status_tab = KeybStatusTab(self.keyboard.keyboardModel)
        self.keyb_script_tab = KeybScriptTab(self.keyboard.keyboardModel)

        tab_widget.addTab(self.console_tab, 'console')
        tab_widget.addTab(self.keyb_script_tab, 'keyboard script')
        tab_widget.addTab(self.rgb_matrix_tab, 'rgb matrix')
        tab_widget.addTab(self.layer_switch_tab, 'layer auto switch')
        tab_widget.addTab(self.keyb_config_tab, 'keyboard config')
        tab_widget.addTab(self.keyb_status_tab, 'keyboard status')

        self.setCentralWidget(tab_widget)
        #-----------------------------------------------------------
        # connect signals
        self.keyboard.signal_console_output.connect(self.console_tab.update_text)
        self.keyboard.signal_default_layer.connect(self.layer_switch_tab.update_default_layer)
        self.keyboard.signal_macwin_mode.connect(self.keyb_config_tab.update_macwin_mode)
        self.keyboard.signal_config_model.connect(self.keyb_config_tab.update_view_model)
        self.keyboard.signal_status_model.connect(self.keyb_status_tab.update_view_model)
        self.keyboard.signal_config.connect(self.keyb_config_tab.update_view)
        self.keyboard.signal_status.connect(self.keyb_status_tab.update_view)

        self.console_tab.signal_cli_command.connect(self.keyboard.keyb_set_cli_command)
        self.rgb_matrix_tab.rgb_video_tab.signal_rgb_image.connect(self.keyboard.keyb_set_rgb_image)
        self.rgb_matrix_tab.rgb_animation_tab.signal_rgb_image.connect(self.keyboard.keyb_set_rgb_image)
        self.rgb_matrix_tab.rgb_audio_tab.signal_rgb_image.connect(self.keyboard.keyb_set_rgb_image)
        self.rgb_matrix_tab.rgb_dynld_animation_tab.signal_dynld_function.connect(self.keyboard.keyb_set_dynld_function)
        self.layer_switch_tab.signal_keyb_set_layer.connect(self.keyboard.keyb_set_default_layer)
        self.keyb_config_tab.signal_keyb_set_config.connect(self.keyboard.keyb_set_config)
        self.keyb_config_tab.signal_keyb_get_config.connect(self.keyboard.keyb_get_config)
        self.keyb_config_tab.signal_macwin_mode.connect(self.keyboard.keyb_set_macwin_mode)
        self.keyb_script_tab.signal_run_script.connect(self.keyboard.run_script)
        self.keyb_status_tab.signal_keyb_get_status.connect(self.keyboard.keyb_get_status)

        #-----------------------------------------------------------
        # window focus listener
        try:
            self.winfocus_listener = WinFocusListener()
            self.winfocus_listener.signal_winfocus.connect(self.layer_switch_tab.on_winfocus)
            self.winfocus_listener.start()
        except:
            pass

        #-----------------------------------------------------------
        # start keyboard communication
        self.keyboard.start()

    def closeEvent(self, event):
        try:
            self.winfocus_listener.stop()
        except:
            pass
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

    keyboard_models = FirmataKeyboard.load_keyboard_models()
    keyboards = []
    print (f"keyboards: {keyboard_models[0]}")
    for model in keyboard_models[0].values():
        if device_attached(model.VID, model.PID):
            print (f"keyboard found: {model.NAME} ({hex(model.VID)}:{hex(model.PID)})")
            keyboards.append(model.NAME)

    return keyboards, keyboard_models[0]

#-------------------------------------------------------------------------------
def main(keyboard_vid_pid):
    from PySide6.QtCore import QLocale
    locale = QLocale("C")
    QLocale.setDefault(locale)
    app = QApplication(sys.argv)
    #app.setStyle('Windows')
    app.setStyle('Fusion')

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

parser = argparse.ArgumentParser(description="keyboard vendor/product id")
parser.add_argument('--vid', required=False, type=lambda x: int(x, 16),
                    help='keyboard vid in hex')
parser.add_argument('--pid', required=False, type=lambda x: int(x, 16),
                    help='keyboard pid in hex')
args = parser.parse_args()

main((args.vid, args.pid))
