import json
import os
import sys
import tempfile
import unittest

class _DummySignal:
    def __init__(self, *args, **kwargs): pass
    def emit(self, *args, **kwargs): pass

class _DummyWidget:
    def __init__(self, *args, **kwargs): pass

class _DummyCheckBox(_DummyWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._checked = True
    def isChecked(self): return self._checked
    def setChecked(self, v): self._checked = v
    def stateChanged(self): return _DummySignal()

class _DummyComboBox(_DummyWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._items = []
        self._index = 0
    def addItem(self, t): self._items.append(t)
    def addItems(self, items): self._items.extend(items)
    def setCurrentIndex(self, i): self._index = i
    def currentIndex(self): return self._index
    def currentText(self): return self._items[self._index] if self._items else ""
    def currentIndexChanged(self): return _DummySignal()
    def setItemDelegate(self, *a): pass
    def setMinimumWidth(self, *a): pass

class _DummyLineEdit(_DummyWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = ""
    def setText(self, t): self._text = t
    def text(self): return self._text
    def setPlaceholderText(self, *a): pass
    def setFixedWidth(self, *a): pass
    def setValidator(self, *a): pass
    def textChanged(self): return _DummySignal()

class _DummyTextEdit(_DummyWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = ""
    def append(self, line): self._text += line + "\n"
    def toPlainText(self): return self._text
    def setPlainText(self, t): self._text = t
    def setReadOnly(self, *a): pass
    def setMaximumHeight(self, *a): pass
    def textChanged(self): return _DummySignal()

class _DummyPushButton(_DummyWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clicked = _DummySignal()

class _DummyFileDialog:
    @staticmethod
    def getOpenFileName(*args, **kwargs): return ("", "")

class _DummyLayout(_DummyWidget):
    def __init__(self, *args, **kwargs): pass
    def addWidget(self, *a, **kw): pass
    def addLayout(self, *a): pass
    def addStretch(self, *a): pass
    def setAlignment(self, *a): pass

class _DummyFontMetrics:
    def __init__(self, *args, **kwargs): pass
    def height(self): return 20

class _DummyDebugTracer:
    def __init__(self, *args, **kwargs): pass
    def tr(self, *a, **kw): pass

class _DummyWSServer:
    def __init__(self, *args, **kwargs): pass
    def start(self): pass
    def stop(self): pass
    def wait(self): pass

def _install_stubs():
    import types
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Qt = types.SimpleNamespace(AlignTop=0, LeftButton=1, CheckState=lambda x: x)
    qtcore.Signal = _DummySignal
    qtwidgets = types.ModuleType("PySide6.QtWidgets")
    for name in ["QWidget", "QVBoxLayout", "QHBoxLayout", "QLabel", "QLineEdit",
                  "QPushButton", "QTextEdit", "QComboBox", "QFileDialog", "QCheckBox",
                  "QStyledItemDelegate"]:
        setattr(qtwidgets, name, _DummyWidget)
    qtwidgets.QCheckBox = _DummyCheckBox
    qtwidgets.QTextEdit = _DummyTextEdit
    qtwidgets.QLineEdit = _DummyLineEdit
    qtwidgets.QComboBox = _DummyComboBox
    qtwidgets.QPushButton = _DummyPushButton
    qtwidgets.QFileDialog = _DummyFileDialog
    qtwidgets.QVBoxLayout = _DummyLayout
    qtwidgets.QHBoxLayout = _DummyLayout
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QFont = type
    qtgui.QFontMetrics = _DummyFontMetrics
    qtgui.QIntValidator = type
    qtgui.QMouseEvent = type
    pyside6 = types.ModuleType("PySide6")
    pyside6.QtCore = qtcore
    pyside6.QtWidgets = qtwidgets
    pyside6.QtGui = qtgui
    debug_tracer = types.ModuleType("DebugTracer")
    debug_tracer.DebugTracer = _DummyDebugTracer
    ws_server = types.ModuleType("WSServer")
    ws_server.WSServer = _DummyWSServer
    sys.modules.setdefault("PySide6", pyside6)
    sys.modules.setdefault("PySide6.QtCore", qtcore)
    sys.modules.setdefault("PySide6.QtWidgets", qtwidgets)
    sys.modules.setdefault("PySide6.QtGui", qtgui)
    sys.modules.setdefault("DebugTracer", debug_tracer)
    sys.modules.setdefault("WSServer", ws_server)

_install_stubs()

from LayerAutoSwitchTab import LayerAutoSwitchTab, CONFIG_FILE
from ModuleAutoSwitchTab import ModuleAutoSwitchTab


class TestLayerAutoSwitchConfig(unittest.TestCase):
    def setUp(self):
        self.config_file = CONFIG_FILE
        self._backup = None
        if os.path.exists(self.config_file):
            with open(self.config_file) as f:
                self._backup = f.read()

    def tearDown(self):
        if os.path.exists(self.config_file):
            os.unlink(self.config_file)
        if self._backup is not None:
            with open(self.config_file, "w") as f:
                f.write(self._backup)

    def test_save_and_load_round_trip(self):
        tab = LayerAutoSwitchTab.__new__(LayerAutoSwitchTab)
        tab.num_program_selectors = 3
        tab.num_keyb_layers = 8
        tab.dbg = _DummyDebugTracer()
        tab.deflayer_selector = _DummyComboBox()
        tab.deflayer_selector.addItems([str(i) for i in range(8)])
        tab.deflayer_selector.setCurrentIndex(3)
        tab.layer_switch_server_checkbox = _DummyCheckBox()
        tab.layer_switch_server_checkbox.setChecked(True)
        tab.layer_switch_server_port = _DummyLineEdit()
        tab.layer_switch_server_port.setText("9999")
        tab.program_selector = [_DummyComboBox() for _ in range(3)]
        tab.layer_selector = [_DummyComboBox() for _ in range(3)]
        tab.match_all_checkbox = [_DummyCheckBox() for _ in range(3)]
        tab.program_selector[0].addItem("P:12345\tChrome\\chrome.exe\tGoogle Chrome")
        tab.program_selector[0].setCurrentIndex(0)
        tab.layer_selector[0].setCurrentIndex(2)
        tab.match_all_checkbox[0].setChecked(False)

        tab._save_config()

        with open(self.config_file) as f:
            config = json.load(f)
        self.assertIn("layer", config)
        self.assertEqual(config["layer"]["default_layer"], 3)
        self.assertTrue(config["layer"]["ws_enabled"])
        self.assertEqual(config["layer"]["ws_port"], "9999")
        self.assertEqual(len(config["layer"]["entries"]), 3)
        self.assertEqual(config["layer"]["entries"][0]["layer"], 2)
        self.assertFalse(config["layer"]["entries"][0]["match_all"])


class TestModuleAutoSwitchConfig(unittest.TestCase):
    def setUp(self):
        self.config_file = CONFIG_FILE
        self._backup = None
        if os.path.exists(self.config_file):
            with open(self.config_file) as f:
                self._backup = f.read()

    def tearDown(self):
        if os.path.exists(self.config_file):
            os.unlink(self.config_file)
        if self._backup is not None:
            with open(self.config_file, "w") as f:
                f.write(self._backup)

    def test_save_and_load_round_trip(self):
        tab = ModuleAutoSwitchTab.__new__(ModuleAutoSwitchTab)
        tab.num_entries = 3
        tab.dbg = _DummyDebugTracer()
        tab.enabled_checkbox = _DummyCheckBox()
        tab.enabled_checkbox.setChecked(False)
        tab.default_module_input = _DummyLineEdit()
        tab.default_module_input.setText("/path/to/default.bin")
        tab.program_selectors = [_DummyComboBox() for _ in range(3)]
        tab.module_inputs = [_DummyLineEdit() for _ in range(3)]
        tab.match_all_checkbox = [_DummyCheckBox() for _ in range(3)]
        tab.program_selectors[0].addItem("P:67890\tCode\\code.exe\tVS Code")
        tab.program_selectors[0].setCurrentIndex(0)
        tab.module_inputs[0].setText("/path/to/module.bin")
        tab.match_all_checkbox[0].setChecked(True)

        tab._save_config()

        with open(self.config_file) as f:
            config = json.load(f)
        self.assertIn("module", config)
        self.assertFalse(config["module"]["enabled"])
        self.assertEqual(config["module"]["default_module"], "/path/to/default.bin")
        self.assertEqual(len(config["module"]["entries"]), 3)
        self.assertEqual(config["module"]["entries"][0]["module_path"], "/path/to/module.bin")
        self.assertTrue(config["module"]["entries"][0]["match_all"])


if __name__ == "__main__":
    unittest.main()
