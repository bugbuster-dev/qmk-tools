import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit,
    QFileDialog, QCheckBox,
)

from DebugTracer import DebugTracer
from LayerAutoSwitchTab import ProgramSelectorComboBox
from ModuleBuild import MODULE_SRAM_SLOT_BASE_ID


class ModuleAutoSwitchTab(QWidget):
    signal_load_module = Signal(int, bytearray)
    num_entries = 4

    def __init__(self):
        self.dbg = DebugTracer(zones={'D': 0}, obj=self)
        self.sram_slot = MODULE_SRAM_SLOT_BASE_ID  # slot 8
        self.current_module = None  # track currently loaded module path
        super().__init__()
        self.init_gui()

    def init_gui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop)

        # Enable checkbox
        self.enabled_checkbox = QCheckBox("Enable auto-switch", self)
        self.enabled_checkbox.setChecked(True)
        layout.addWidget(self.enabled_checkbox)

        # Default module section
        default_layout = QHBoxLayout()
        default_layout.addWidget(QLabel("Default module:"))
        self.default_module_input = QLineEdit()
        self.default_module_input.setPlaceholderText("path/to/default_module.bin")
        default_layout.addWidget(self.default_module_input, 1)
        self.default_browse_btn = QPushButton("Browse...")
        self.default_browse_btn.clicked.connect(self.browse_default_module)
        default_layout.addWidget(self.default_browse_btn)
        layout.addLayout(default_layout)

        # Focus log
        self.label = QLabel(
            "Foreground application focus is logged below.\n"
            "Select a program from the dropdown and assign a module .bin file.\n"
            "Select '-' to clear an entry."
        )
        layout.addWidget(self.label)

        self.winfocus_textedit = QTextEdit()
        self.winfocus_textedit.setReadOnly(True)
        self.winfocus_textedit.setMaximumHeight(150)
        self.winfocus_textedit.textChanged.connect(self.limit_lines)
        layout.addWidget(self.winfocus_textedit)

        # Program entries
        self.program_selectors = []
        self.module_inputs = []
        for i in range(self.num_entries):
            entry_layout = QHBoxLayout()
            ps = ProgramSelectorComboBox(self.winfocus_textedit)
            ps.addItems(["" for _ in range(5)])
            ps.setCurrentIndex(0)
            self.program_selectors.append(ps)
            entry_layout.addWidget(ps)

            mod_input = QLineEdit()
            mod_input.setPlaceholderText("path/to/module.bin")
            self.module_inputs.append(mod_input)
            entry_layout.addWidget(mod_input, 1)

            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda checked=False, idx=i: self.browse_module(idx))
            entry_layout.addWidget(browse_btn)

            layout.addLayout(entry_layout)

        self.setLayout(layout)

    def browse_default_module(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Module Binary", "", "Binary Files (*.bin);;All Files (*)"
        )
        if path:
            self.default_module_input.setText(path)

    def browse_module(self, index):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Module Binary", "", "Binary Files (*.bin);;All Files (*)"
        )
        if path:
            self.module_inputs[index].setText(path)

    def on_winfocus(self, line):
        if not self.enabled_checkbox.isChecked():
            return
        self.update_winfocus_text(line)
        focus_parts = line.split("\t")
        focus_proc = focus_parts[1].strip() if len(focus_parts) > 1 else ""
        focus_title = focus_parts[2].strip() if len(focus_parts) > 2 else ""

        for i in range(self.num_entries):
            selected = self.program_selectors[i].currentText().strip()
            if not selected or selected == "-":
                continue
            sel_parts = selected.split("\t")
            sel_proc = sel_parts[1].strip() if len(sel_parts) > 1 else ""
            sel_title = sel_parts[2].strip() if len(sel_parts) > 2 else ""
            if focus_proc == sel_proc and focus_title == sel_title:
                module_path = self.module_inputs[i].text().strip()
                if module_path and os.path.exists(module_path):
                    self._load_module(module_path)
                return

        # No match — load default module
        default_path = self.default_module_input.text().strip()
        if default_path and os.path.exists(default_path):
            self._load_module(default_path)

    def _load_module(self, path):
        if self.current_module == path:
            return  # already loaded
        try:
            with open(path, "rb") as f:
                binary = f.read()
            self.signal_load_module.emit(self.sram_slot, bytearray(binary))
            self.current_module = path
            self.dbg.tr('D', f"Loaded module: {path}")
        except OSError as e:
            self.dbg.tr('E', f"Failed to load {path}: {e}")

    def update_winfocus_text(self, line):
        self.winfocus_textedit.append(line)

    def limit_lines(self):
        lines = self.winfocus_textedit.toPlainText().split('\n')
        if len(lines) > 10:
            self.winfocus_textedit.setPlainText('\n'.join(lines[-10:]))
