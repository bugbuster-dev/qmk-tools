import os
import sys
import tempfile
import types
import unittest


class _DummySignal:
    def __init__(self, *args, **kwargs):
        self._emitted = None

    def emit(self, *args, **kwargs):
        self._emitted = args


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


class _DebugTracer:
    def __init__(self, *args, **kwargs):
        pass

    def tr(self, *args, **kwargs):
        pass


class _ProgramSelectorComboBox:
    def __init__(self, *args, **kwargs):
        pass

    def addItems(self, *args, **kwargs):
        pass

    def setCurrentIndex(self, *args, **kwargs):
        pass

    def currentText(self):
        return ""


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
        "QLabel",
        "QLineEdit",
        "QPushButton",
        "QTextEdit",
        "QFileDialog",
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
    debug_tracer.DebugTracer = _DebugTracer

    layer_auto_switch = types.ModuleType("LayerAutoSwitchTab")
    layer_auto_switch.ProgramSelectorComboBox = _ProgramSelectorComboBox

    sys.modules.setdefault("PySide6", pyside6)
    sys.modules.setdefault("PySide6.QtCore", qtcore)
    sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)
    sys.modules.setdefault("PySide6.QtGui", qtgui)
    sys.modules.setdefault("DebugTracer", debug_tracer)
    sys.modules.setdefault("LayerAutoSwitchTab", layer_auto_switch)


_install_test_stubs()

from ModuleBuild import MODULE_SRAM_SLOT_BASE_ID


class TestModuleAutoSwitchLoad(unittest.TestCase):
    def test_load_module_emits_signal_with_sram_slot(self):
        """Loading a module emits signal_load_module with slot 8 and file contents."""
        from ModuleAutoSwitchTab import ModuleAutoSwitchTab
        tab = ModuleAutoSwitchTab.__new__(ModuleAutoSwitchTab)
        tab.sram_slot = MODULE_SRAM_SLOT_BASE_ID
        tab.current_module = None
        tab.signal_load_module = _DummySignal()
        tab.dbg = _DebugTracer()

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            bin_path = f.name

        try:
            tab._load_module(bin_path)
            args = tab.signal_load_module._emitted
            self.assertEqual(args[0], MODULE_SRAM_SLOT_BASE_ID)
            self.assertEqual(bytes(args[1]), b"\x00\x01\x02\x03")
            self.assertEqual(tab.current_module, bin_path)
        finally:
            os.unlink(bin_path)

    def test_load_module_skips_if_already_loaded(self):
        """Loading the same module path twice only emits once."""
        from ModuleAutoSwitchTab import ModuleAutoSwitchTab
        tab = ModuleAutoSwitchTab.__new__(ModuleAutoSwitchTab)
        tab.sram_slot = MODULE_SRAM_SLOT_BASE_ID
        emit_count = [0]

        def count_emit(*args):
            emit_count[0] += 1

        tab.signal_load_module = _DummySignal()
        tab.signal_load_module.emit = count_emit
        tab.current_module = None
        tab.dbg = _DebugTracer()

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(b"\x00\x01")
            bin_path = f.name

        try:
            tab._load_module(bin_path)
            tab._load_module(bin_path)
            self.assertEqual(emit_count[0], 1)
        finally:
            os.unlink(bin_path)


if __name__ == "__main__":
    unittest.main()
