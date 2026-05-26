from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QApplication, QMessageBox, QFileDialog
from PySide6.QtGui import QFont, QKeySequence, QKeyEvent, QTextCursor

from DebugTracer import DebugTracer

#-------------------------------------------------------------------------------
class HexEditor(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setFont(QFont("Courier New", 9))
        self.setAcceptRichText(False)  # Only plain text to avoid formatting

    def keyPressEvent(self, event: QKeyEvent):
        if event.matches(QKeySequence.Paste):
            self.handlePaste()
            return

        # Allow undo
        if event.matches(QKeySequence.Undo):
            self.undo()
            return
        # Allow redo
        elif event.matches(QKeySequence.Redo):
            self.redo()
            return

        text = event.text()
        # Only allow hexadecimal characters
        if text.upper() in '0123456789ABCDEF':
            super().keyPressEvent(event)
            self.formatText()
        # Allow backspace and delete
        elif event.key() in (Qt.Key_Backspace, Qt.Key_Delete):
            super().keyPressEvent(event)
            self.formatText()
        # Ignore other keys
        else:
            event.ignore()

    def handlePaste(self):
            clipboard = QApplication.clipboard()
            text = clipboard.text()
            # Validate and clean the pasted text
            cleaned_text = ''.join(filter(lambda x: x.upper() in '0123456789ABCDEF', text.upper()))
            if cleaned_text:
                # Only insert cleaned text
                self.insertPlainText(cleaned_text)
                self.formatText()
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.End)
                self.setTextCursor(cursor)
            else:
                QMessageBox.warning(self, "Invalid Paste Content", "Pasted text contains non-hexadecimal characters.")

    def formatText(self):
        cursor_pos = self.textCursor().position()
        # Remove spaces and newlines for clean formatting
        text = self.toPlainText().replace(" ", "").replace("\n", "")
        # Insert space after every 2 hex characters and newline after every 32 characters
        formatted_text = ' '.join(text[i:i+2] for i in range(0, len(text), 2))
        formatted_text = '\n'.join(formatted_text[i:i+48] for i in range(0, len(formatted_text), 48))  # 32 hex chars + 16 spaces = 48
        self.setPlainText(formatted_text)
        cursor = self.textCursor()
        cursor.setPosition(cursor_pos)
        self.setTextCursor(cursor)

    def is_hex(self, s):
        try:
            int(s, 16)
            return True
        except ValueError:
            return False

    def getBinaryContent(self):
        # Remove spaces and newlines to get a clean hex string
        hex_str = self.toPlainText().replace(" ", "").replace("\n", "")
        try:
            # Convert hex string to a binary array (bytes object)
            data = bytes.fromhex(hex_str)
            return data
        except ValueError:
            # Handle the case where the hex string is invalid
            QMessageBox.warning(self, "Invalid Hex Content", "The content contains non-hexadecimal characters or an incomplete byte.")
            return None

#-------------------------------------------------------------------------------
class RGBDynLDAnimationTab(QWidget):
    signal_dynld_function = Signal(int, bytearray)

    def __init__(self, keyboard=None):
        self.keyboard = keyboard
        self.dbg = DebugTracer(zones={'D':1}, obj=self)
        #---------------------------------------
        super().__init__()
        self.init_gui()

    def init_gui(self):
        layout = QVBoxLayout()

        # --- Source file compilation ---
        hlayout_src = QHBoxLayout()
        hlayout_src.addWidget(QLabel("C source:"))
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("path/to/animation.c")
        hlayout_src.addWidget(self.source_input)
        self.browse_src_btn = QPushButton("Browse")
        self.browse_src_btn.clicked.connect(self.browse_source)
        hlayout_src.addWidget(self.browse_src_btn)
        self.compile_btn = QPushButton("Compile")
        self.compile_btn.clicked.connect(self.compile_source)
        hlayout_src.addWidget(self.compile_btn)
        layout.addLayout(hlayout_src)

        #---------------------------------------
        # dynld animation bin file (pre-built)
        hlayout = QHBoxLayout()
        dynld_bin_label = QLabel("Binary (.bin):")
        self.dynld_bin_input = QLineEdit("dynld_animation.bin")
        hlayout.addWidget(dynld_bin_label)
        hlayout.addWidget(self.dynld_bin_input)
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self.load_dynld_animation_func)
        hlayout.addWidget(self.load_button)
        layout.addLayout(hlayout)

        #---------------------------------------
        self.dynld_funtext_edit = HexEditor()
        self.dynld_funtext_edit.setFixedHeight(400)
        self.load_dynld_animation_func()
        layout.addWidget(self.dynld_funtext_edit)

        #---------------------------------------
        self.send_button = QPushButton("send to keyboard")
        self.send_button.clicked.connect(self.send_dynld_animation_func)
        layout.addWidget(self.send_button)
        layout.addStretch(1)
        self.setLayout(layout)

    def load_dynld_animation_func(self):
        try:
            with open(self.dynld_bin_input.text(), 'rb') as file:
                buf = bytearray(file.read())
                hexbuf = buf.hex(' ')
                self.dynld_funtext_edit.setText(hexbuf)
                self.dynld_funtext_edit.formatText()
        except Exception as e:
            self.dbg.tr('DEBUG', f"error: {e}")

    def browse_source(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Animation Source", "", "C Files (*.c);;All Files (*)"
        )
        if file_path:
            self.source_input.setText(file_path)

    def compile_source(self):
        source = self.source_input.text().strip()
        if not source:
            QMessageBox.warning(self, "No Source", "No C source file specified.")
            return

        if not self.keyboard:
            QMessageBox.warning(self, "No Keyboard", "Keyboard not connected.")
            return

        self.compile_btn.setEnabled(False)
        self.dbg.tr('DEBUG', f"Compiling: {source}")

        try:
            result = self.keyboard.compile(source)
        except Exception as e:
            self.dbg.tr('DEBUG', f"Compile FAILED: {e}")
            QMessageBox.warning(self, "Compile Failed", str(e))
            self.compile_btn.setEnabled(True)
            return

        if result is None or result.get("bin") is None:
            self.dbg.tr('DEBUG', "Compile FAILED")
            QMessageBox.warning(self, "Compile Failed", "Compilation returned no output.")
            self.compile_btn.setEnabled(True)
            return

        bin_data = result["bin"]
        hexbuf = bin_data.hex(' ')
        self.dynld_funtext_edit.setText(hexbuf)
        self.dynld_funtext_edit.formatText()
        self.dbg.tr('DEBUG', f"Compile OK: {len(bin_data)} bytes — ready to send")
        self.compile_btn.setEnabled(True)

    def send_dynld_animation_func(self):
        fundata = self.dynld_funtext_edit.getBinaryContent()
        if fundata:
            DYNLD_ANIMATION_FUNC = 0
            self.signal_dynld_function.emit(DYNLD_ANIMATION_FUNC, fundata)
