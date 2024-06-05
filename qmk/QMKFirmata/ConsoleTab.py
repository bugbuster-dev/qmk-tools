import os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QTextCursor

from DebugTracer import DebugTracer

class ConsoleTab(QWidget):
    signal_cli_command = Signal(str)

    class CommandLineEdit(QLineEdit):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.command_history = []
            self.history_index = 0

        def keyPressEvent(self, event):
            if event.key() == Qt.Key.Key_Up:
                if self.history_index > 0:
                    self.history_index -= 1
                    self.setText(self.command_history[self.history_index])
                    self.selectAll()
                return
            elif event.key() == Qt.Key.Key_Down:
                if self.history_index < len(self.command_history) - 1:
                    self.history_index += 1
                    self.setText(self.command_history[self.history_index])
                elif self.history_index == len(self.command_history) - 1:
                    self.history_index += 1
                    self.clear()
                return
            super().keyPressEvent(event)

        def store_clear_command(self):
            command = self.text().strip()
            if command:
                self.command_history.append(command)
                self.history_index = len(self.command_history)
                self.clear()

    def __init__(self, keyboard_model):
        self.dbg = DebugTracer(zones={'D':0}, obj=self)

        self.keyboard_model = keyboard_model
        try:
            self.keyboard_config = self.keyboard_model.keyb_config()
        except:
            self.keyboard_config = None
        self.dbg.tr('D', "keyboard_model: {} {}", self.keyboard_model, self.keyboard_config)

        self.max_text_length = 2000000
        self.max_console_file_size = self.max_text_length*2
        self.console_text_len = 0
        self.console_file_clear = True

        super().__init__()
        self.init_gui()

    def handle_cli_command(self):
        cmd = self.cli.text()
        self.dbg.tr('D', "cli command: {}", cmd)
        self.signal_cli_command.emit(cmd)
        self.cli.store_clear_command()

    def init_gui(self):
        # console output
        layout = QVBoxLayout()
        self.cli = self.CommandLineEdit()
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        font = QFont()
        font.setFamily("Courier New")
        self.cli.setFont(font)
        self.console_output.setFont(font)
        self.cli.returnPressed.connect(self.handle_cli_command)
        layout.addWidget(self.cli)
        layout.addWidget(self.console_output)
        self.setLayout(layout)

    def update_text(self, text):
        cursor = self.console_output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.console_output.setTextCursor(cursor)
        self.console_output.insertPlainText(text)
        self.console_output.ensureCursorVisible()
        self.console_text_len += len(text)
        self.limit_text()

    def save_to_file(self, filename, clear=False):
        # check file size and append
        try:
            filesize = os.path.getsize(filename)
            if clear:
                try:
                    os.remove(filename)
                    filesize = 0
                except Exception as e:
                    self.dbg.tr('E', "remove console log: {}", e)
        except:
            filesize = 0
        if filesize < self.max_console_file_size:
            try:
                with open(filename, "a") as file:
                    file.write(self.console_output.toPlainText())
            except Exception as e:
                self.dbg.tr('E', "save_to_file: {}", e)

    def limit_text(self):
        if self.console_text_len >= self.max_text_length:
            self.save_to_file("console_output.txt", self.console_file_clear)
            self.console_file_clear = False
            self.console_output.clear()
            self.console_text_len = 0
