import struct
import sys
import types
import unittest


class _DummySignal:
    def __init__(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


class _DummyWidget:
    def __init__(self, *args, **kwargs):
        pass


class _DummyQObject:
    def __init__(self, *args, **kwargs):
        pass


class _DummyFont:
    def __init__(self, *args, **kwargs):
        pass


class _DummyTextCursor:
    End = 0


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


class _DummyDebugTracer:
    def __init__(self, *args, **kwargs):
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

    debug_tracer = types.ModuleType("DebugTracer")
    debug_tracer.DebugTracer = _DummyDebugTracer

    sys.modules.setdefault("PySide6", pyside6)
    sys.modules.setdefault("PySide6.QtCore", qtcore)
    sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)
    sys.modules.setdefault("PySide6.QtGui", qtgui)
    sys.modules.setdefault("DebugTracer", debug_tracer)


_install_test_stubs()

from ModuleTab import ModuleTab


class _FakeCheckBox:
    def __init__(self, checked):
        self._checked = checked

    def isChecked(self):
        return self._checked


class ModuleTabHookBitmapTest(unittest.TestCase):
    def test_prepare_binary_for_load_patches_selected_hook_bitmap(self):
        tab = ModuleTab.__new__(ModuleTab)
        tab.last_build_result = {
            "binary": bytes(32),
        }
        tab.hook_checkboxes = [
            ("combo_should_trigger", _FakeCheckBox(True)),
            ("process_combo_event", _FakeCheckBox(False)),
            ("get_combo_term", _FakeCheckBox(True)),
        ]
        tab.log = lambda _message: None

        binary = tab._prepare_binary_for_load()

        self.assertEqual(0x00000005, struct.unpack_from("<I", binary, 12)[0])

    def test_prepare_binary_for_load_allows_zero_selected_hooks(self):
        tab = ModuleTab.__new__(ModuleTab)
        tab.last_build_result = {
            "binary": bytes(32),
        }
        tab.hook_checkboxes = [
            ("combo_should_trigger", _FakeCheckBox(False)),
            ("init", _FakeCheckBox(False)),
        ]

        binary = tab._prepare_binary_for_load()

        self.assertEqual(0x00000000, struct.unpack_from("<I", binary, 12)[0])

    def test_selected_hook_bitmap_maps_reserved_labels_to_reserved_bits(self):
        tab = ModuleTab.__new__(ModuleTab)
        tab.hook_checkboxes = [
            ("init", _FakeCheckBox(True)),
            ("deinit", _FakeCheckBox(True)),
            ("hook_5", _FakeCheckBox(False)),
        ]

        self.assertEqual(0x00000018, tab._selected_hook_bitmap())


if __name__ == "__main__":
    unittest.main()
