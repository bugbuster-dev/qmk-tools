import struct
import sys
import types
import unittest


class _DummyQObject:
    def __init__(self, *args, **kwargs):
        pass


class _DummySignal:
    def __init__(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


class _DummyQImage:
    Format_RGB888 = 0
    Format_BGR888 = 1


class _DummyQColor:
    def __init__(self, *args, **kwargs):
        pass

    def getRgb(self):
        return (0, 0, 0, 0)

    def rgb(self):
        return 0


class _DummyQPainter:
    def __init__(self, *args, **kwargs):
        pass

    def drawImage(self, *args, **kwargs):
        pass

    def end(self):
        pass


class _DummyWidget:
    def __init__(self, *args, **kwargs):
        pass


class _DummyFont:
    def __init__(self, *args, **kwargs):
        pass


class _DummyTextCursor:
    End = 0


class _DummyDebugTracer:
    def __init__(self, *args, **kwargs):
        pass

    def enabled(self, *args, **kwargs):
        return False

    def tr(self, *args, **kwargs):
        pass


def _install_test_stubs():
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Qt = types.SimpleNamespace()
    qtcore.QObject = _DummyQObject
    qtcore.Signal = _DummySignal

    qtwidgets = types.ModuleType("PySide6.QtWidgets")
    for name in [
        "QWidget",
        "QVBoxLayout",
        "QHBoxLayout",
        "QGridLayout",
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QTextEdit",
        "QComboBox",
        "QFileDialog",
        "QGroupBox",
        "QCheckBox",
    ]:
        setattr(qtwidgets, name, _DummyWidget)

    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QFont = _DummyFont
    qtgui.QTextCursor = _DummyTextCursor
    qtgui.QImage = _DummyQImage
    qtgui.QColor = _DummyQColor
    qtgui.QPainter = _DummyQPainter

    pyside6 = types.ModuleType("PySide6")
    pyside6.QtCore = qtcore
    pyside6.QtWidgets = qtwidgets
    pyside6.QtGui = qtgui

    pyfirmata2 = types.ModuleType("pyfirmata2")
    pyfirmata2.Board = type("Board", (), {})
    pyfirmata2.util = types.SimpleNamespace(Iterator=lambda *args, **kwargs: None)
    pyfirmata2.START_SYSEX = 0
    pyfirmata2.END_SYSEX = 0
    pyfirmata2.REPORT_FIRMWARE = 0
    pyfirmata2.STRING_DATA = 0
    pyfirmata2.BOARDS = {"arduino": None}

    serial = types.ModuleType("serial")
    serial.Serial = object
    serial.tools = types.SimpleNamespace(
        list_ports=types.SimpleNamespace(comports=lambda: [])
    )

    sys.modules.setdefault("PySide6", pyside6)
    sys.modules.setdefault("PySide6.QtCore", qtcore)
    sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)
    sys.modules.setdefault("PySide6.QtGui", qtgui)
    sys.modules.setdefault("pyfirmata2", pyfirmata2)
    sys.modules.setdefault("serial", serial)
    sys.modules.setdefault("numpy", types.ModuleType("numpy"))

    serial_raw_hid = types.ModuleType("SerialRawHID")
    serial_raw_hid.SerialRawHID = object
    sys.modules.setdefault("SerialRawHID", serial_raw_hid)

    debug_tracer = types.ModuleType("DebugTracer")
    debug_tracer.DebugTracer = _DummyDebugTracer
    sys.modules.setdefault("DebugTracer", debug_tracer)


_install_test_stubs()

from QMKataKeyboard import QMKataKeyboard, QMKataKeybCmd


class _FakeSignal:
    def __init__(self):
        self.emitted = []

    def emit(self, payload):
        self.emitted.append(payload)


class _FakeDbg:
    def __init__(self):
        self.messages = []

    def enabled(self, *_args, **_kwargs):
        return True

    def tr(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class ModuleSummaryEndianTest(unittest.TestCase):
    def test_module_summary_magics_are_always_little_endian(self):
        magics = [
            0x4D4F444C,
            0x00000000,
            0x01020304,
            0x4D4F444C,
            0xAABBCCDD,
            0x11223344,
            0x00000001,
            0xFFFFFFFF,
        ]
        slot_count = len(magics)
        payload = bytearray([9, QMKataKeybCmd.ID_MODULE, 0xFF])
        for magic in magics:
            payload.extend(struct.pack("<I", magic))

        keyboard = QMKataKeyboard.__new__(QMKataKeyboard)
        keyboard.dbg = _FakeDbg()
        keyboard.pack_endian = ">"
        keyboard.sysex_response_seq = {}
        keyboard._sysex_data_to_bytearray = lambda _data: payload
        keyboard.signal_module_status = _FakeSignal()

        keyboard.sysex_response_handler(0)

        self.assertEqual(1, len(keyboard.signal_module_status.emitted))
        self.assertEqual(
            {
                "type": "summary",
                "slot_count": slot_count,
                "slots": [1, 0, 0, 1, 0, 0, 0, 0],
                "magics": magics,
            },
            keyboard.signal_module_status.emitted[0],
        )

    def test_module_summary_ignores_malformed_payload_length(self):
        payload = bytearray([3, QMKataKeybCmd.ID_MODULE, 0xFF, 0x34, 0x12, 0x00])

        keyboard = QMKataKeyboard.__new__(QMKataKeyboard)
        keyboard.dbg = _FakeDbg()
        keyboard.pack_endian = ">"
        keyboard.sysex_response_seq = {}
        keyboard._sysex_data_to_bytearray = lambda _data: payload
        keyboard.signal_module_status = _FakeSignal()

        keyboard.sysex_response_handler(0)

        self.assertEqual([], keyboard.signal_module_status.emitted)
        self.assertTrue(keyboard.dbg.messages)

    def test_module_slot_fields_are_always_little_endian(self):
        payload = bytearray([7, QMKataKeybCmd.ID_MODULE, 3])
        payload.extend(struct.pack("<I", 0x4D4F444C))
        payload.extend(struct.pack("<H", 0x0001))
        payload.extend(struct.pack("<I", 0x11223344))

        keyboard = QMKataKeyboard.__new__(QMKataKeyboard)
        keyboard.dbg = _FakeDbg()
        keyboard.pack_endian = ">"
        keyboard.sysex_response_seq = {}
        keyboard._sysex_data_to_bytearray = lambda _data: payload
        keyboard.signal_module_status = _FakeSignal()

        keyboard.sysex_response_handler(0)

        self.assertEqual(
            [
                {
                    "type": "slot",
                    "slot_id": 3,
                    "magic": 0x4D4F444C,
                    "flags": 0x0001,
                    "hook_bitmap": 0x11223344,
                }
            ],
            keyboard.signal_module_status.emitted,
        )


if __name__ == "__main__":
    unittest.main()
