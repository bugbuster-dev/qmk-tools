import json
import os
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit,
    QFileDialog, QCheckBox,
)

from DebugTracer import DebugTracer
from LayerAutoSwitchTab import ProgramSelectorComboBox, CONFIG_FILE
from ModuleBuild import MODULE_SRAM_SLOT_BASE_ID


class ModuleAutoSwitchTab(QWidget):
    signal_load_module = Signal(int, bytearray)
    num_entries = 10

    def __init__(self):
        self.dbg = DebugTracer(zones={'D': 0}, obj=self)
        self.sram_slot = MODULE_SRAM_SLOT_BASE_ID  # slot 8
        self.current_module = None  # track currently loaded module path
        super().__init__()
        self.init_gui()
        self._load_config()

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
        self.match_all_checkbox = []
        for i in range(self.num_entries):
            entry_layout = QHBoxLayout()
            ps = ProgramSelectorComboBox(self.winfocus_textedit)
            ps.addItems(["" for _ in range(5)])
            ps.setCurrentIndex(0)
            self.program_selectors.append(ps)
            entry_layout.addWidget(ps, 2)

            mod_input = QLineEdit()
            mod_input.setPlaceholderText("path/to/module.bin")
            self.module_inputs.append(mod_input)
            entry_layout.addWidget(mod_input, 1)

            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda checked=False, idx=i: self.browse_module(idx))
            entry_layout.addWidget(browse_btn)

            cb = QCheckBox("all")
            cb.setChecked(True)
            self.match_all_checkbox.append(cb)
            entry_layout.addWidget(cb)

            layout.addLayout(entry_layout)

        self.setLayout(layout)

        # Wire auto-save on every change
        self.enabled_checkbox.stateChanged.connect(self._save_config)
        self.default_module_input.textChanged.connect(self._save_config)
        for i in range(self.num_entries):
            self.program_selectors[i].currentIndexChanged.connect(self._save_config)
            self.module_inputs[i].textChanged.connect(self._save_config)
            self.match_all_checkbox[i].stateChanged.connect(self._save_config)

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
        focus_parts = line.split("\t")
        focus_title = focus_parts[2].strip() if len(focus_parts) > 2 else ""
        if focus_title in ("Task Switching", "Task View"):
            return
        self.update_winfocus_text(line)
        focus_parts = line.split("\t")
        focus_pid = focus_parts[0].strip() if len(focus_parts) > 0 else ""
        focus_proc = focus_parts[1].strip() if len(focus_parts) > 1 else ""

        for i in range(self.num_entries):
            selected = self.program_selectors[i].currentText().strip()
            if not selected or selected == "-":
                continue
            sel_parts = selected.split("\t")
            sel_pid = sel_parts[0].strip() if len(sel_parts) > 0 else ""
            sel_proc = sel_parts[1].strip() if len(sel_parts) > 1 else ""
            if self.match_all_checkbox[i].isChecked():
                match = focus_proc == sel_proc
            else:
                match = focus_proc == sel_proc and focus_pid == sel_pid
            if match:
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
        scrollbar = self.winfocus_textedit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def limit_lines(self):
        lines = self.winfocus_textedit.toPlainText().split('\n')
        if len(lines) > 10:
            self.winfocus_textedit.setPlainText('\n'.join(lines[-10:]))

    def _save_config(self):
        try:
            config = {}
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE) as f:
                        config = json.load(f)
                except json.JSONDecodeError:
                    pass
            entries = []
            for i in range(self.num_entries):
                entries.append({
                    "program": self.program_selectors[i].currentText(),
                    "module_path": self.module_inputs[i].text(),
                    "match_all": self.match_all_checkbox[i].isChecked(),
                })
            config["module"] = {
                "enabled": self.enabled_checkbox.isChecked(),
                "default_module": self.default_module_input.text(),
                "entries": entries,
            }
            with open(CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            self.dbg.tr('E', f"save config: {e}")

    def _load_config(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                return
            with open(CONFIG_FILE) as f:
                config = json.load(f)
            mod = config.get("module", {})
            self.enabled_checkbox.setChecked(mod.get("enabled", True))
            dm = mod.get("default_module", "")
            if dm:
                self.default_module_input.setText(dm)
            entries = mod.get("entries", [])
            for i in range(self.num_entries):
                if i < len(entries) and entries[i].get("program"):
                    self.program_selectors[i].clear()
                    self.program_selectors[i].addItem(entries[i]["program"])
                    self.program_selectors[i].setCurrentIndex(0)
                    mp = entries[i].get("module_path", "")
                    if mp:
                        self.module_inputs[i].setText(mp)
                    self.match_all_checkbox[i].setChecked(entries[i].get("match_all", True))
        except Exception as e:
            self.dbg.tr('E', f"load config: {e}")
