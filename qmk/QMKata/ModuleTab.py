import os
import struct

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QComboBox,
    QFileDialog, QGroupBox, QCheckBox,
)
from PySide6.QtGui import QFont, QTextCursor

from DebugTracer import DebugTracer
from ModuleBuild import (
    ModuleBuild, HOOK_NAMES, MODULE_HEADER_SIZE,
    MODULE_FLASH_BASE, MODULE_FLASH_SLOT_SIZE,
    MODULE_SRAM_SLOT_BASE_ID, MODULE_SRAM_SLOT_SIZE, MODULE_SRAM_DEFAULT_BASE,
    MODULE_HEADER_FLAG_SRAM,
    hook_name_for_index, hook_index_for_name,
)


def _slot_base_addr(keyboard_model, slot_id):
    """Resolve slot_id to its absolute address (flash or SRAM).

    Flash slots (0..MODULE_SRAM_SLOT_BASE_ID-1): queried via
    keyboard.module_flash_layout() when available, else falls back to the
    legacy MODULE_FLASH_BASE + slot_id * MODULE_FLASH_SLOT_SIZE formula.

    SRAM slots (>= MODULE_SRAM_SLOT_BASE_ID): queried via
    keyboard.module_sram_layout() when available, else falls back to
    MODULE_SRAM_DEFAULT_BASE + (slot_id - MODULE_SRAM_SLOT_BASE_ID) *
    MODULE_SRAM_SLOT_SIZE. The default is the top-of-RAM address for an
    STM32F401xC firmware with a 4 KB carve-out. Real builds should
    resolve via GccMapfile reading the g_module_sram symbol from the
    firmware .map.
    """
    if slot_id >= MODULE_SRAM_SLOT_BASE_ID:
        if keyboard_model is not None and hasattr(keyboard_model, "module_sram_layout"):
            for sid, base, _size in keyboard_model.module_sram_layout():
                if sid == slot_id:
                    return base
        return MODULE_SRAM_DEFAULT_BASE + (slot_id - MODULE_SRAM_SLOT_BASE_ID) * MODULE_SRAM_SLOT_SIZE

    if keyboard_model is not None and hasattr(keyboard_model, "module_flash_layout"):
        for sid, base, _size in keyboard_model.module_flash_layout():
            if sid == slot_id:
                return base
    return MODULE_FLASH_BASE + slot_id * MODULE_FLASH_SLOT_SIZE


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
        self.last_build_target = None  # 'flash' or 'sram'
        self.hook_checkboxes = []
        self.init_gui()

    def init_gui(self):
        layout = QVBoxLayout()

        # --- Slot control section ---
        slot_group = QGroupBox("Module Slots")
        slot_layout = QHBoxLayout()
        slot_layout.addWidget(QLabel("Slot:"))
        self.slot_combo = QComboBox()
        for i in range(8):
            self.slot_combo.addItem(f"Slot {i}", i)
        self.slot_combo.addItem("Slot 8 (SRAM)", 8)
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
        self.load_bin_button = QPushButton("Load binary...")
        self.load_bin_button.clicked.connect(self.load_binary_file)
        slot_layout.addWidget(self.load_bin_button)
        slot_group.setLayout(slot_layout)
        layout.addWidget(slot_group)

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

        self.hooks_group = QGroupBox("Hooks")
        self.hooks_layout = QVBoxLayout()
        self.hooks_group.setLayout(self.hooks_layout)
        self.hooks_group.setVisible(False)
        layout.addWidget(self.hooks_group)

        # --- Slot status grid ---
        status_group = QGroupBox("Slot Status")
        self.status_grid = QGridLayout()
        self.status_grid.addWidget(QLabel("Slot"), 0, 0)
        self.status_grid.addWidget(QLabel("Status"), 0, 1)
        self.status_grid.addWidget(QLabel("Hooks"), 0, 2)
        self.slot_labels = []
        for i in range(9):
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
            self.last_build_target = None
        self._clear_hook_checkboxes()
        self.load_button.setEnabled(False)

    def _clear_hook_checkboxes(self):
        while self.hooks_layout.count():
            item = self.hooks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.hook_checkboxes = []
        self.hooks_group.setVisible(False)

    def _rebuild_hook_checkboxes(self, hooks):
        self._clear_hook_checkboxes()
        for hook_name in hooks:
            checkbox = QCheckBox(hook_name)
            checkbox.setChecked(True)
            self.hooks_layout.addWidget(checkbox)
            self.hook_checkboxes.append((hook_name, checkbox))
        self.hooks_group.setVisible(bool(hooks))

    def _selected_hook_bitmap(self):
        hook_bitmap = 0
        for hook_name, checkbox in self.hook_checkboxes:
            if checkbox.isChecked():
                hook_idx = hook_index_for_name(hook_name)
                if hook_idx is not None:
                    hook_bitmap |= (1 << hook_idx)
        return hook_bitmap

    def _prepare_binary_for_load(self, slot_id):
        binary = bytearray(self.last_build_result['binary'])
        hook_bitmap = self._selected_hook_bitmap()
        struct.pack_into("<I", binary, 12, hook_bitmap)
        if not (hook_bitmap & (1 << 3)):
            struct.pack_into("<I", binary, 20, 0)
        if not (hook_bitmap & (1 << 4)):
            struct.pack_into("<I", binary, 24, 0)

        relocs = self.last_build_result.get('relocs', [])

        # Pre-built binary: no relocs to apply, CRC already correct.
        # Just return the modified bytes (hook bitmap may have changed).
        if not relocs and self.module_build is None:
            return bytes(binary)

        # Built-in path: apply relocations and recompute CRC.
        kb = getattr(self, "keyboard", None)
        keyboard_model = getattr(kb, "keyboardModel", None) if kb is not None else None
        slot_addr = _slot_base_addr(keyboard_model, slot_id)
        load_flags = MODULE_HEADER_FLAG_SRAM if slot_id >= MODULE_SRAM_SLOT_BASE_ID else 0
        return self.module_build.apply_relocations_and_crc(
            bytes(binary),
            relocs,
            slot_addr,
            flags=load_flags,
        )

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

          # Determine build target from selected slot.
        selected_slot = self.slot_combo.currentData()
        build_target = 'sram' if selected_slot >= MODULE_SRAM_SLOT_BASE_ID else 'flash'
        self.last_build_target = build_target
        result = self.module_build.build(source, target=build_target)
        if result is None:
            if self.module_build.last_error:
                self.log(f"Build FAILED: {self.module_build.last_error}")
            else:
                self.log("Build FAILED")
            self._clear_hook_checkboxes()
            self.load_button.setEnabled(False)
            self.last_build_result = None
            self.last_build_target = None
            return

        self.last_build_result = result
        self._rebuild_hook_checkboxes(result['hooks'])
        self.load_button.setEnabled(True)
        self.log(f"Build OK: {result['size']} bytes, hooks: {', '.join(result['hooks'])}")

        # Autosave binary next to source
        bin_path = os.path.splitext(source)[0] + ".bin"
        with open(bin_path, "wb") as f:
            f.write(result['binary'])
        self.log(f"  saved: {bin_path}")
        self.log(f"  hook_bitmap: 0x{result['hook_bitmap']:08X}")
        self.log(f"  fits_slot: {'yes' if result['fits_slot'] else 'no'}")

    def load_module(self):
        """Load last built module to selected slot."""
        if self.last_build_result is None:
            self.log("Error: No module built yet")
            return
        slot_id = self.slot_combo.currentData()

        # Check build target matches selected slot type
        if self.last_build_target == 'sram' and slot_id < MODULE_SRAM_SLOT_BASE_ID:
            self.log("Error: Module was built for SRAM — cannot upload to flash slot.")
            self.log("         Select Slot 8 (SRAM) and try again.")
            return
        if self.last_build_target == 'flash' and slot_id >= MODULE_SRAM_SLOT_BASE_ID:
            self.log("Error: Module was built for flash — cannot upload to SRAM slot.")
            self.log("         Select a flash slot (0-7) and try again.")
            return

        binary = self._prepare_binary_for_load(slot_id)
        self.log(f"Loading module to slot {slot_id} ({len(binary)} bytes)...")
        self.signal_load_module.emit(slot_id, binary)

    def load_binary_file(self):
        """Browse for a pre-built .bin file and load it directly."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Module Binary", "", "Binary Files (*.bin);;All Files (*)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "rb") as f:
                binary = f.read()
        except OSError as e:
            self.log(f"Error reading file: {e}")
            return

        if len(binary) < 32:
            self.log(f"Error: file too small ({len(binary)} bytes), need ≥32 byte header")
            return

        magic, version, flags, code_size, hook_bitmap, hook_off, init_off, deinit_off, crc = \
            struct.unpack("<IHHIIIIII", binary[:32])

        if magic != 0x4D4F444C:
            self.log(f"Error: invalid magic 0x{magic:08X}, expected 0x4D4F444C")
            return

        slot_id = self.slot_combo.currentData()
        if slot_id >= MODULE_SRAM_SLOT_BASE_ID and code_size > MODULE_SRAM_SLOT_SIZE:
            self.log(f"Error: module too large for SRAM slot ({code_size} > {MODULE_SRAM_SLOT_SIZE})")
            return

        if (flags & MODULE_HEADER_FLAG_SRAM) and slot_id < MODULE_SRAM_SLOT_BASE_ID:
            self.log("Error: Binary is SRAM-relocated - cannot load to flash slot.")
            self.log("         Select Slot 8 (SRAM) and try again.")
            return

        # Decode hook names from bitmap
        hook_names = []
        for bit in range(32):
            if hook_bitmap & (1 << bit):
                hook_names.append(hook_name_for_index(bit))

        import os
        self.log(f"Loading binary: {os.path.basename(file_path)}")
        self.log(f"  version: {version}  size: {code_size}  hooks: {', '.join(hook_names)}")
        self.log(f"  hook_bitmap: 0x{hook_bitmap:08X}")

        # Store as a pseudo build result so load_module() can use it.
        # Relocs are already applied at build time; pass empty list.
        self.last_build_result = {
            'binary': binary,
            'hooks': hook_names,
            'hook_bitmap': hook_bitmap,
            'size': code_size,
            'fits_slot': True,
            'relocs': [],
        }
        self._rebuild_hook_checkboxes(hook_names)
        self.load_button.setEnabled(True)
        self.log(f"Ready — select slot and click 'Load to Slot'")

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
            # flags (data['flags']) is reserved in the current module header
            # format; firmware ignores it and the host always sends 0. The
            # status label set by the 'summary' branch ("Occupied") already
            # conveys everything the user can act on, so we do not override
            # it here.
            hook_bitmap = data.get('hook_bitmap', 0)
            if slot_id < len(self.slot_labels):
                if magic == 0x4D4F444C:  # MODULE_HEADER_MAGIC
                    # Decode hook names
                    hook_names = []
                    for bit_index in range(32):
                        if hook_bitmap & (1 << bit_index):
                            hook_names.append(hook_name_for_index(bit_index))
                    self.slot_labels[slot_id][1].setText(
                        ", ".join(hook_names) if hook_names else "none"
                    )
                else:
                    self.slot_labels[slot_id][0].setText("Empty")
                    self.slot_labels[slot_id][1].setText("—")
