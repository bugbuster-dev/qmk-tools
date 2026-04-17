# Copyright (C) 2024 bugbuster
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA.

# this code is like a box of bugs, you never know what you're gonna get
import os, sys, argparse, struct

from PySide6 import QtCore
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
)
from PySide6.QtWidgets import (
    QTextEdit,
    QPushButton,
    QLabel,
    QLineEdit,
    QTreeView,
    QScrollArea,
    QTableWidget,
    QHeaderView,
)
from PySide6.QtWidgets import QComboBox, QMessageBox
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtGui import QIntValidator, QDoubleValidator
from PySide6.QtGui import QStandardItemModel, QStandardItem

from DebugTracer import DebugTracer

try:
    from WinFocusListener import WinFocusListener
except:
    pass

from QMKataKeyboard import QMKataKeyboard
from QMKataKeycodes import KeycodeResolver
from ConsoleTab import ConsoleTab
from WSServer import WSServer
from RGBVideoTab import RGBVideoTab
from RGBAudioTab import RGBAudioTab
from RGBAnimationTab import RGBAnimationTab, CodeTextEdit
from RGBDynLDAnimationTab import RGBDynLDAnimationTab
from LayerAutoSwitchTab import LayerAutoSwitchTab

if __name__ != "__main__":
    exit()


# -------------------------------------------------------------------------------
class RGBMatrixTab(QWidget):
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

        self.rgb_video_tab = RGBVideoTab(
            (app_width, app_height), self, self.rgb_matrix_size
        )
        self.rgb_animation_tab = RGBAnimationTab(self.rgb_matrix_size)
        self.rgb_audio_tab = RGBAudioTab(self.rgb_matrix_size)
        self.rgb_dynld_animation_tab = RGBDynLDAnimationTab()

        self.tab_widget.addTab(self.rgb_video_tab, "video")
        self.tab_widget.addTab(self.rgb_animation_tab, "animation")
        self.tab_widget.addTab(self.rgb_audio_tab, "audio")
        self.tab_widget.addTab(self.rgb_dynld_animation_tab, "dynld animation")

        layout.addWidget(self.tab_widget)
        self.setLayout(layout)


# -------------------------------------------------------------------------------
class TreeviewWidget(QWidget):
    def __init__(self, keyboard_model):
        self.keyboard_model = keyboard_model
        self.endian = "little"
        try:
            if self.keyboard_model.MCU[2].startswith("be"):
                self.endian = "big"
        except:
            pass
        super().__init__()

    def init_gui(self):
        if not hasattr(self, "layout"):
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
        self.dbg.tr("D", "update_view_model: {}", view_model)
        self.tree_view.setModel(view_model)
        if view_model:
            try:
                view_model.dataChanged.connect(self.update_keyb_data)
            except Exception as e:
                self.dbg.tr("D", "update_view_model: {}", e)

    def update_view(self, item_data):  # update from keyboard
        try:
            item_id = item_data[0]
        except Exception as e:
            self.dbg.tr("D", "update_view: {}", e)
            return
        field_values = item_data[1]
        model = self.tree_view.model()
        item = model.item(item_id - 1, 0)
        if self.dbg.enabled("D"):
            self.dbg.tr("D", "update_view: {} {}", item.text(), item_data)
        for i in range(item.rowCount()):  # todo: row number may not match field id
            try:
                value_item = item.child(i, 3)
                type_item = item.child(i, 1)
                field_value = field_values[i + 1]
                if type(field_value) == bytearray:
                    value_item.setFont(
                        QFont("Courier New", 7)
                    )  # todo move this to update_view_model
                    hex_string = ""
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
                        val = int.from_bytes(
                            field_value[i : i + item_size], self.endian
                        )
                        hex_string += format_str % val
                        if (
                            i % (items_per_line * item_size)
                            == (items_per_line * item_size) - item_size
                        ):
                            hex_string += "\n"

                    formatted_string = hex_string
                    field_value = formatted_string
                    # field_value = field_value.hex(' ')
                value_item.setText(f"{field_value}")
            except Exception as e:
                self.dbg.tr("D", "update_view: {}", e)


# -------------------------------------------------------------------------------
class KeybConfigTab(TreeviewWidget):
    signal_keyb_set_config = Signal(tuple)
    signal_keyb_get_config = Signal(int)
    signal_macwin_mode = Signal(str)

    def __init__(self, keyboard_model):
        self.dbg = DebugTracer(zones={"D": 0}, obj=self)

        self.keyboard_model = keyboard_model
        super().__init__(keyboard_model)
        self.init_gui()

    def update_keyb_data(self, tl, br, roles):
        # self.dbg.tr('D', "update_keyb_data: topleft:{tl}, roles:{roles}", tl=tl, roles=roles)
        update = False
        if roles:
            for role in roles:
                if role == Qt.EditRole:
                    update = True

        if update:  # todo update only if changed via ui not from update_view
            try:
                item = self.tree_view.model().itemFromIndex(tl)
                config_item = item.parent()
                config_id = config_item.row() + 1

                field_values = {}
                for i in range(config_item.rowCount()):
                    field = config_item.child(i, 0)
                    value = config_item.child(i, 3)
                    # print(f"{field.text()} = {value.text()}")
                    if value.text() == "":
                        return
                    if not value.flags() & Qt.ItemIsEditable:
                        return
                    field_values[i + 1] = value.text()
            except Exception as e:
                self.dbg.tr("D", "update_keyb_config: {}", e)
                return
            config = (config_id, field_values)
            self.dbg.tr("D", "update_keyb_config:signal emit {}", config)
            self.signal_keyb_set_config.emit(config)

    def update_keyb_macwin_mode(self):
        macwin_mode = self.mac_win_mode_selector.currentText()
        self.signal_macwin_mode.emit(macwin_mode)

    def init_gui(self):
        hlayout = QHBoxLayout()
        config_label = QLabel("keyboard configuration")
        config_refresh_button = QPushButton("refresh")
        config_refresh_button.clicked.connect(
            lambda: self.signal_keyb_get_config.emit(0)
        )
        hlayout.addWidget(config_label)
        hlayout.addWidget(config_refresh_button)
        hlayout.addStretch(1)
        # ---------------------------------------
        # mac/win mode
        macwin_label = QLabel("mac/win mode")
        self.mac_win_mode_selector = QComboBox()
        self.mac_win_mode_selector.addItem("m")
        self.mac_win_mode_selector.addItem("w")
        self.mac_win_mode_selector.addItem("-")
        hlayout.addWidget(macwin_label)
        hlayout.addWidget(self.mac_win_mode_selector)
        self.mac_win_mode_selector.setCurrentIndex(1)
        self.mac_win_mode_selector.currentIndexChanged.connect(
            self.update_keyb_macwin_mode
        )
        self.mac_win_mode_selector.setFixedWidth(40)
        hlayout.addStretch(1)

        self.layout = QVBoxLayout()
        self.layout.addLayout(hlayout)
        super().init_gui()

    def update_macwin_mode(self, macwin_mode):
        self.mac_win_mode_selector.setCurrentIndex(0 if macwin_mode == "m" else 1)


# -------------------------------------------------------------------------------
class ComboConfigTab(QWidget):
    signal_keyb_get_combo = Signal(int)
    signal_keyb_set_combo = Signal(int, list, int)

    def __init__(self, keyboard_model, resolver=None):
        self.dbg = DebugTracer(zones={"D": 0, "E": 1}, obj=self)
        self.keyboard_model = keyboard_model
        self.resolver = resolver or KeycodeResolver()
        super().__init__()
        self.init_gui()

    def init_gui(self):
        layout = QVBoxLayout()

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("Dynamic Combo Configuration"))
        refresh_btn = QPushButton("Refresh All")
        refresh_btn.clicked.connect(self.refresh_all)
        header.addWidget(refresh_btn)
        header.addStretch(1)
        layout.addLayout(header)

        # Scroll area for slots
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        self.slots_layout = QVBoxLayout(container)

        self.slot_widgets = []
        for i in range(16):
            slot_widget = self.create_slot_widget(i)
            self.slot_widgets.append(slot_widget)
            self.slots_layout.addWidget(slot_widget)

        self.slots_layout.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self.setLayout(layout)

    def create_slot_widget(self, slot):
        widget = QFrame()
        widget.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(widget)

        label = QLabel(f"Slot {slot}:")
        label.setFixedWidth(60)

        keys_edit = QLineEdit()
        keys_edit.setPlaceholderText("Keys (e.g. KC_A, KC_B)")
        keys_edit.setFixedWidth(200)

        code_edit = QLineEdit()
        code_edit.setPlaceholderText("Result (e.g. LCTL(KC_C))")
        code_edit.setFixedWidth(150)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(lambda checked=False, s=slot: self.save_combo(s))

        layout.addWidget(label)
        layout.addWidget(QLabel("Keys:"))
        layout.addWidget(keys_edit)
        layout.addWidget(QLabel("Result:"))
        layout.addWidget(code_edit)
        layout.addWidget(save_btn)

        # Store references to inputs
        widget.keys_input = keys_edit
        widget.code_input = code_edit

        return widget

    def refresh_all(self):
        for i in range(16):
            self.signal_keyb_get_combo.emit(i)

    @staticmethod
    def _split_keycode_list(text):
        """Split comma-separated keycode expressions, respecting parentheses."""
        items = []
        depth = 0
        current = []
        for ch in text:
            if ch == "," and depth == 0:
                items.append("".join(current))
                current = []
            else:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                current.append(ch)
        if current:
            items.append("".join(current))
        return items

    def update_slot(self, data):
        if not data:
            return
        slot = data["slot"]
        if slot < 16:
            widget = self.slot_widgets[slot]
            keys_str = ", ".join(
                [self.resolver.value_to_display(k) for k in data["keys"] if k != 0]
            )
            widget.keys_input.setText(keys_str)
            widget.code_input.setText(self.resolver.value_to_display(data["keycode"]))

    def save_combo(self, slot):
        widget = self.slot_widgets[slot]
        try:
            keys_str = widget.keys_input.text()
            keys = [
                self.resolver.resolve(k.strip())
                for k in self._split_keycode_list(keys_str)
                if k.strip()
            ]
            keycode = self.resolver.resolve(widget.code_input.text().strip())
            self.signal_keyb_set_combo.emit(slot, keys, keycode)
        except Exception as e:
            self.dbg.tr("E", "Failed to parse combo input: {}", e)
            # Brief visual feedback: set placeholder to show error
            widget.code_input.setPlaceholderText(f"Error: {e}")


# -------------------------------------------------------------------------------
class TapDanceConfigTab(QWidget):
    QK_TAP_DANCE = 0x5700
    COLUMNS = ["Slot", "Tap x1", "Tap x2", "Tap x3", "Hold"]
    NUM_SLOTS = 8

    signal_keyb_get_tap_dance = Signal(int)
    signal_keyb_set_tap_dance = Signal(int, int, int, int, int)

    def __init__(self, pack_endian, resolver):
        super().__init__()
        self.pack_endian = pack_endian
        self.resolver = resolver
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget(self.NUM_SLOTS, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)

        for row in range(self.NUM_SLOTS):
            # Save button showing VIA keycode for this slot
            via_kc = self.QK_TAP_DANCE + row
            btn = QPushButton(f"Save  [0x{via_kc:04X}]")
            btn.setToolTip(
                f"TD({row}) = 0x{via_kc:04X}\n"
                f"Use this keycode in VIA to assign this tap dance to a key"
            )
            btn.clicked.connect(lambda checked=False, r=row: self.save_slot(r))
            self.table.setCellWidget(row, 0, btn)
            # Keycode fields
            for col in range(1, len(self.COLUMNS)):
                edit = QLineEdit()
                edit.setPlaceholderText("KC_NO")
                self.table.setCellWidget(row, col, edit)

        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh All")
        refresh_btn.clicked.connect(self.refresh_all)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        hint = QLabel(
            "assign TD(n) keycodes in VIA to map tap dance slots to physical keys"
        )
        hint.setStyleSheet("color: gray; font-style: italic;")
        btn_row.addWidget(hint)
        layout.addLayout(btn_row)

    def refresh_all(self):
        for slot in range(self.NUM_SLOTS):
            self.signal_keyb_get_tap_dance.emit(slot)

    def update_slot(self, slot, data):
        """Called when signal_tap_dance fires. data is 8 raw bytes (4×uint16 LE)."""
        if slot >= self.NUM_SLOTS:
            return
        if len(data) < 8:
            return
        kc1, kc2, kc3, hold = struct.unpack(self.pack_endian + "HHHH", data[:8])
        values = [kc1, kc2, kc3, hold]
        for col_idx, kc in enumerate(values):
            edit = self.table.cellWidget(slot, col_idx + 1)
            if edit:
                edit.setText(self.resolver.value_to_display(kc) if kc else "")

    def save_slot(self, row):
        """Resolve keycode fields and send SET command for this row."""
        kcs = []
        error = False
        for col in range(1, len(self.COLUMNS)):
            edit = self.table.cellWidget(row, col)
            text = edit.text().strip() if edit else ""
            if not text:
                kcs.append(0)
                continue
            try:
                kc = self.resolver.resolve(text)
                kcs.append(kc)
                edit.setStyleSheet("")
            except Exception as e:
                edit.setStyleSheet("background: #ffcccc")
                edit.setPlaceholderText(str(e))
                error = True
        if not error:
            self.signal_keyb_set_tap_dance.emit(row, *kcs)


# -------------------------------------------------------------------------------
class LeaderConfigTab(QWidget):
    QK_LEADER = 0x7C58
    COLUMNS = ["Slot", "Seq 1", "Seq 2", "Seq 3", "Seq 4", "Seq 5", "Action"]
    NUM_SLOTS = 8

    signal_keyb_get_leader = Signal(int)
    signal_keyb_set_leader = Signal(int, list, int)

    def __init__(self, pack_endian, resolver):
        super().__init__()
        self.pack_endian = pack_endian
        self.resolver = resolver
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.table = QTableWidget(self.NUM_SLOTS, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)

        for row in range(self.NUM_SLOTS):
            btn = QPushButton(f"Save")
            btn.setToolTip(
                f"Leader slot {row}\n"
                f"Assign QK_LEADER (0x{self.QK_LEADER:04X}) to a key in VIA"
            )
            btn.clicked.connect(lambda checked=False, r=row: self.save_slot(r))
            self.table.setCellWidget(row, 0, btn)
            for col in range(1, len(self.COLUMNS)):
                edit = QLineEdit()
                edit.setPlaceholderText("KC_NO")
                self.table.setCellWidget(row, col, edit)

        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh All")
        refresh_btn.clicked.connect(self.refresh_all)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        hint = QLabel(
            f"assign QK_LEADER (0x{self.QK_LEADER:04X}) to a key in VIA, "
            f"or use a combo/tap dance slot"
        )
        hint.setStyleSheet("color: gray; font-style: italic;")
        btn_row.addWidget(hint)
        layout.addLayout(btn_row)

    def refresh_all(self):
        for slot in range(self.NUM_SLOTS):
            self.signal_keyb_get_leader.emit(slot)

    def update_slot(self, slot, data):
        """Called when signal_leader fires. data is 12 raw bytes (5x uint16 seq + 1x uint16 kc)."""
        if slot >= self.NUM_SLOTS:
            return
        if len(data) < 12:
            return
        values = struct.unpack(self.pack_endian + "HHHHHH", data[:12])
        # values = (seq0, seq1, seq2, seq3, seq4, keycode)
        for col_idx, kc in enumerate(values):
            edit = self.table.cellWidget(slot, col_idx + 1)
            if edit:
                edit.setText(self.resolver.value_to_display(kc) if kc else "")

    def save_slot(self, row):
        """Resolve keycode fields and send SET command for this row."""
        seq = []
        keycode = 0
        error = False
        # Columns 1-5 are sequence, column 6 is action keycode
        for col in range(1, len(self.COLUMNS)):
            edit = self.table.cellWidget(row, col)
            text = edit.text().strip() if edit else ""
            if not text:
                if col <= 5:
                    seq.append(0)
                # keycode stays 0
                continue
            try:
                kc = self.resolver.resolve(text)
                if col <= 5:
                    seq.append(kc)
                else:
                    keycode = kc
                edit.setStyleSheet("")
            except Exception as e:
                edit.setStyleSheet("background: #ffcccc")
                edit.setPlaceholderText(str(e))
                error = True
        if not error:
            self.signal_keyb_set_leader.emit(row, seq, keycode)


# -------------------------------------------------------------------------------
class KeyFunctionsTab(QWidget):
    def __init__(self, keyboard_model, keyboard, resolver=None):
        super().__init__()
        self._build_ui(keyboard_model, keyboard, resolver)

    def _build_ui(self, keyboard_model, keyboard, resolver):
        layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()

        self.combo_tab = ComboConfigTab(keyboard_model, resolver)
        self.tap_dance_tab = TapDanceConfigTab(keyboard.pack_endian, resolver)
        self.leader_tab = LeaderConfigTab(keyboard.pack_endian, resolver)

        self.tab_widget.addTab(self.combo_tab, "combo")
        self.tab_widget.addTab(self.tap_dance_tab, "tap dance")
        self.tab_widget.addTab(self.leader_tab, "leader")

        layout.addWidget(self.tab_widget)


# -------------------------------------------------------------------------------
class KeybStatusTab(TreeviewWidget):
    signal_keyb_get_status = Signal(int, int)

    def __init__(self, keyboard_model):
        self.dbg = DebugTracer(zones={"D": 0}, obj=self)

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
        status_refresh_button.clicked.connect(
            lambda: self.signal_keyb_get_status.emit(int(every_msec_edit.text()), 0)
        )

        hlayout.addWidget(status_label)
        hlayout.addWidget(status_refresh_button)
        hlayout.addWidget(every_label)
        hlayout.addWidget(every_msec_edit)
        hlayout.addStretch(1)

        self.layout = QVBoxLayout()
        self.layout.addLayout(hlayout)
        super().init_gui()


# -------------------------------------------------------------------------------
class KeybScriptTab(QWidget):
    signal_run_script = Signal(str, object)
    signal_script_output = Signal(str)

    def __init__(self, keyboard_model):
        self.dbg = DebugTracer(zones={"D": 0}, obj=self)
        # ---------------------------------------
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


# -------------------------------------------------------------------------------
app_width = 800
app_height = 900


class MainWindow(QMainWindow):
    def __init__(self, keyboard_vid_pid, firmware_path=None):
        self.keyboard_vid_pid = keyboard_vid_pid
        self.firmware_path = firmware_path
        super().__init__()
        self.init_gui()

    def init_gui(self):
        self.setWindowTitle("QMKata")
        self.setGeometry(100, 100, app_width, app_height)
        self.setFixedSize(app_width, app_height)

        # instantiate qmkata keyboard
        self.keyboard = QMKataKeyboard(
            port=None, vid_pid=self.keyboard_vid_pid, firmware_path=self.firmware_path
        )
        num_keyb_layers = self.keyboard.num_layers()

        # -----------------------------------------------------------
        # add tabs
        tab_widget = QTabWidget()
        self.console_tab = ConsoleTab(self.keyboard.keyboardModel)
        self.rgb_matrix_tab = RGBMatrixTab(self.keyboard.keyboardModel)
        self.layer_switch_tab = LayerAutoSwitchTab(num_keyb_layers)
        self.keyb_config_tab = KeybConfigTab(self.keyboard.keyboardModel)
        self.keyb_status_tab = KeybStatusTab(self.keyboard.keyboardModel)
        self.keyb_script_tab = KeybScriptTab(self.keyboard.keyboardModel)
        resolver = (
            KeycodeResolver(self.firmware_path)
            if self.firmware_path
            else KeycodeResolver()
        )
        self.key_functions_tab = KeyFunctionsTab(
            self.keyboard.keyboardModel, self.keyboard, resolver
        )

        tab_widget.addTab(self.console_tab, "console")
        tab_widget.addTab(self.keyb_script_tab, "keyboard script")
        tab_widget.addTab(self.rgb_matrix_tab, "rgb matrix")
        tab_widget.addTab(self.layer_switch_tab, "layer auto switch")
        tab_widget.addTab(self.keyb_config_tab, "keyboard config")
        tab_widget.addTab(self.keyb_status_tab, "keyboard status")
        tab_widget.addTab(self.key_functions_tab, "key functions")

        self.setCentralWidget(tab_widget)
        # -----------------------------------------------------------
        # connect signals
        self.keyboard.signal_console_output.connect(self.console_tab.update_text)
        self.keyboard.signal_default_layer.connect(
            self.layer_switch_tab.update_default_layer
        )
        self.keyboard.signal_macwin_mode.connect(
            self.keyb_config_tab.update_macwin_mode
        )
        self.keyboard.signal_config_model.connect(
            self.keyb_config_tab.update_view_model
        )
        self.keyboard.signal_status_model.connect(
            self.keyb_status_tab.update_view_model
        )
        self.keyboard.signal_config.connect(self.keyb_config_tab.update_view)
        self.keyboard.signal_status.connect(self.keyb_status_tab.update_view)

        self.console_tab.signal_cli_command.connect(self.keyboard.keyb_set_cli_command)
        self.rgb_matrix_tab.rgb_video_tab.signal_rgb_image.connect(
            self.keyboard.keyb_set_rgb_image
        )
        self.rgb_matrix_tab.rgb_animation_tab.signal_rgb_image.connect(
            self.keyboard.keyb_set_rgb_image
        )
        self.rgb_matrix_tab.rgb_audio_tab.signal_rgb_image.connect(
            self.keyboard.keyb_set_rgb_image
        )
        self.rgb_matrix_tab.rgb_audio_tab.signal_peak_levels.connect(
            self.rgb_matrix_tab.rgb_animation_tab.on_audio_peak_levels
        )
        self.rgb_matrix_tab.rgb_dynld_animation_tab.signal_dynld_function.connect(
            self.keyboard.keyb_set_dynld_function
        )
        self.layer_switch_tab.signal_keyb_set_layer.connect(
            self.keyboard.keyb_set_default_layer
        )
        self.keyb_config_tab.signal_keyb_set_config.connect(
            self.keyboard.keyb_set_config
        )
        self.keyb_config_tab.signal_keyb_get_config.connect(
            self.keyboard.keyb_get_config
        )
        self.keyb_config_tab.signal_macwin_mode.connect(
            self.keyboard.keyb_set_macwin_mode
        )
        self.keyb_script_tab.signal_run_script.connect(self.keyboard.run_script)
        self.keyb_status_tab.signal_keyb_get_status.connect(
            self.keyboard.keyb_get_status
        )
        self.keyboard.signal_combo.connect(self.key_functions_tab.combo_tab.update_slot)
        self.key_functions_tab.combo_tab.signal_keyb_get_combo.connect(
            self.keyboard.keyb_get_combo
        )
        self.key_functions_tab.combo_tab.signal_keyb_set_combo.connect(
            self.keyboard.keyb_set_combo
        )
        self.keyboard.signal_tap_dance.connect(
            self.key_functions_tab.tap_dance_tab.update_slot
        )
        self.key_functions_tab.tap_dance_tab.signal_keyb_get_tap_dance.connect(
            self.keyboard.keyb_get_tap_dance
        )
        self.key_functions_tab.tap_dance_tab.signal_keyb_set_tap_dance.connect(
            self.keyboard.keyb_set_tap_dance
        )
        self.keyboard.signal_leader.connect(
            self.key_functions_tab.leader_tab.update_slot
        )
        self.key_functions_tab.leader_tab.signal_keyb_get_leader.connect(
            self.keyboard.keyb_get_leader
        )
        self.key_functions_tab.leader_tab.signal_keyb_set_leader.connect(
            self.keyboard.keyb_set_leader
        )

        # -----------------------------------------------------------
        # window focus listener
        try:
            self.winfocus_listener = WinFocusListener()
            self.winfocus_listener.signal_winfocus.connect(
                self.layer_switch_tab.on_winfocus
            )
            self.winfocus_listener.start()
        except:
            pass

        # -----------------------------------------------------------
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
        self.setWindowTitle("select keyboard")
        self.setText("keyboard:")

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


# -------------------------------------------------------------------------------
def main(keyboard_vid_pid, firmware_path=None):
    from PySide6.QtCore import QLocale

    locale = QLocale("C")
    QLocale.setDefault(locale)
    app = QApplication(sys.argv)
    # app.setStyle('Windows')
    app.setStyle("Fusion")

    selected_keyboard = ""
    if keyboard_vid_pid[0] == None:
        keyboards, keyb_models = QMKataKeyboard.attached_keyboards()
        if len(keyboards):
            selection_popup = KeyboardSelectionPopup(keyboards)
            if selection_popup.exec():
                selected_keyboard = selection_popup.selected_keyboard()
                keyboard_vid_pid = (
                    keyb_models[selected_keyboard].VID,
                    keyb_models[selected_keyboard].PID,
                )

    main_window = MainWindow(keyboard_vid_pid, firmware_path=firmware_path)
    main_window.show()
    sys.exit(app.exec())


parser = argparse.ArgumentParser(description="keyboard vendor/product id")
parser.add_argument(
    "--vid", required=False, type=lambda x: int(x, 16), help="keyboard vid in hex"
)
parser.add_argument(
    "--pid", required=False, type=lambda x: int(x, 16), help="keyboard pid in hex"
)
parser.add_argument(
    "--firmware-path",
    required=False,
    type=str,
    help="path to QMK firmware root (enables keycode name resolution)",
)
args = parser.parse_args()

main((args.vid, args.pid), firmware_path=args.firmware_path)
