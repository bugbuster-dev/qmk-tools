from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox,
    QFileDialog, QGroupBox,
)
from PySide6.QtGui import QFont, QTextCursor

from DebugTracer import DebugTracer
from ModuleBuild import ModuleBuild, HOOK_NAMES


class ModuleTab(QWidget):
    """Tab for building, loading, and unloading keyboard modules."""

    # Signals to keyboard
    signal_load_module = Signal(int, bytearray)    # (slot_id, binary_data)
    signal_unload_module = Signal(int)              # (slot_id,)
    signal_get_module_summary = Signal()
    signal_get_module = Signal(int)                 # (slot_id,)

    def __init__(self, keyboard_model=None, keyboard=None):
        self.dbg = DebugTracer(zones={'D': 1}, obj=self)
        super().__init__()
        self.keyboard = keyboard
        self.module_build = None  # set up when build is first triggered
        self.last_build_result = None
        self.init_gui()

    def init_gui(self):
        layout = QVBoxLayout()

        # --- Source file section ---
        source_group = QGroupBox("Module Source")
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("C source:"))
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("path/to/module.c")
        self.source_input.textChanged.connect(self.on_source_changed)
        source_layout.addWidget(self.source_input)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_source)
        source_layout.addWidget(self.browse_button)
        self.build_button = QPushButton("Build")
        self.build_button.clicked.connect(self.build_module)
        source_layout.addWidget(self.build_button)
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # --- Slot control section ---
        slot_group = QGroupBox("Module Slots")
        slot_layout = QHBoxLayout()
        slot_layout.addWidget(QLabel("Slot:"))
        self.slot_combo = QComboBox()
        for i in range(8):
            self.slot_combo.addItem(f"Slot {i}", i)
        slot_layout.addWidget(self.slot_combo)
        self.load_button = QPushButton("Load to Slot")
        self.load_button.clicked.connect(self.load_module)
        self.load_button.setEnabled(False)
        slot_layout.addWidget(self.load_button)
        self.unload_button = QPushButton("Unload Slot")
        self.unload_button.clicked.connect(self.unload_module)
        slot_layout.addWidget(self.unload_button)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_slots)
        slot_layout.addWidget(self.refresh_button)
        slot_group.setLayout(slot_layout)
        layout.addWidget(slot_group)

        # --- Slot status grid ---
        status_group = QGroupBox("Slot Status")
        self.status_grid = QGridLayout()
        self.status_grid.addWidget(QLabel("Slot"), 0, 0)
        self.status_grid.addWidget(QLabel("Status"), 0, 1)
        self.status_grid.addWidget(QLabel("Hooks"), 0, 2)
        self.slot_labels = []
        for i in range(8):
            slot_label = QLabel(f"{i}")
            status_label = QLabel("—")
            hooks_label = QLabel("—")
            self.status_grid.addWidget(slot_label, i + 1, 0)
            self.status_grid.addWidget(status_label, i + 1, 1)
            self.status_grid.addWidget(hooks_label, i + 1, 2)
            self.slot_labels.append((status_label, hooks_label))
        status_group.setLayout(self.status_grid)
        layout.addWidget(status_group)

        limitation_label = QLabel(
            "Note: loading a slot erases other modules in the same sector "
            "(slots 0-3 share one sector, 4-7 share another)."
        )
        limitation_label.setWordWrap(True)
        layout.addWidget(limitation_label)

        # --- Log area ---
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Courier New", 9))
        self.log_area.setMaximumHeight(200)
        layout.addWidget(self.log_area)

        layout.addStretch(1)
        self.setLayout(layout)

    def log(self, message):
        """Append message to the log area."""
        self.log_area.append(message)
        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_area.setTextCursor(cursor)

    def browse_source(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Module Source", "", "C Files (*.c);;All Files (*)"
        )
        if file_path:
            self.source_input.setText(file_path)

    def on_source_changed(self):
        if self.last_build_result is not None:
            self.last_build_result = None
        self.load_button.setEnabled(False)

    def build_module(self):
        """Build module from source file."""
        source = self.source_input.text().strip()
        if not source:
            self.log("Error: No source file specified")
            return

        self.log(f"Building module from: {source}")

        # Initialize ModuleBuild if needed
        if self.module_build is None:
            try:
                from GccToolchain import GccToolchain
                firmware_path = None
                if self.keyboard and hasattr(self.keyboard, 'firmware_path'):
                    firmware_path = self.keyboard.firmware_path
                toolchain = GccToolchain(
                    getattr(self.keyboard, 'keyboardModel', None)
                    and self.keyboard.keyboardModel.TOOLCHAIN or None,
                    firmware_path=firmware_path,
                )
                self.module_build = ModuleBuild(
                    toolchain, firmware_path=firmware_path
                )
            except Exception as e:
                self.log(f"Error initializing build system: {e}")
                return

        result = self.module_build.build(source)
        if result is None:
            self.log("Build FAILED")
            self.load_button.setEnabled(False)
            self.last_build_result = None
            return

        self.last_build_result = result
        self.load_button.setEnabled(True)
        self.log(f"Build OK: {result['size']} bytes, hooks: {', '.join(result['hooks'])}")
        self.log(f"  hook_bitmap: 0x{result['hook_bitmap']:08X}")

    def load_module(self):
        """Load last built module to selected slot."""
        if self.last_build_result is None:
            self.log("Error: No module built yet")
            return
        slot_id = self.slot_combo.currentData()
        binary = bytearray(self.last_build_result['binary'])
        self.log(f"Loading module to slot {slot_id} ({len(binary)} bytes)...")
        self.signal_load_module.emit(slot_id, binary)

    def unload_module(self):
        """Unload module from selected slot."""
        slot_id = self.slot_combo.currentData()
        self.log(f"Unloading slot {slot_id}...")
        self.signal_unload_module.emit(slot_id)

    def refresh_slots(self):
        """Request slot status from keyboard."""
        self.log("Refreshing slot status...")
        self.signal_get_module_summary.emit()

    def update_module_status(self, data):
        """Handle module status updates from keyboard.

        Called when keyboard.signal_module_status fires.
        data is a dict with 'type' key:
          - 'summary': {'slot_count': N, 'slots': [status_bytes]}
          - 'slot': {'slot_id': N, 'magic': M, 'flags': F, 'hook_bitmap': HB}
        """
        msg_type = data.get('type')
        if msg_type == 'summary':
            slots = data.get('slots', [])
            for i, status in enumerate(slots):
                if i < len(self.slot_labels):
                    status_text = "Occupied" if status else "Empty"
                    self.slot_labels[i][0].setText(status_text)
                    if not status:
                        self.slot_labels[i][1].setText("—")
            for i in range(len(slots), len(self.slot_labels)):
                self.slot_labels[i][0].setText("—")
                self.slot_labels[i][1].setText("—")
            # Request details for occupied slots
            for i, status in enumerate(slots):
                if status:
                    self.signal_get_module.emit(i)
            self.log(f"Slot status refreshed: {len(slots)} slots")

        elif msg_type == 'slot':
            slot_id = data.get('slot_id', 0)
            magic = data.get('magic', 0)
            flags = data.get('flags', 0)
            hook_bitmap = data.get('hook_bitmap', 0)
            if slot_id < len(self.slot_labels):
                if magic == 0x4D4F444C:  # MODULE_HEADER_MAGIC
                    enabled = "Enabled" if (flags & 1) else "Disabled"
                    self.slot_labels[slot_id][0].setText(enabled)
                    # Decode hook names
                    hook_names = []
                    for name, idx in HOOK_NAMES.items():
                        if hook_bitmap & (1 << idx):
                            hook_names.append(name)
                    self.slot_labels[slot_id][1].setText(
                        ", ".join(hook_names) if hook_names else "none"
                    )
                else:
                    self.slot_labels[slot_id][0].setText("Empty")
                    self.slot_labels[slot_id][1].setText("—")
