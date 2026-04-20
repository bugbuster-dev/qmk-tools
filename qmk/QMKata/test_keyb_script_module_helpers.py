import sys
import types
import unittest
from pathlib import Path


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


class _DummyDebugTracer:
    def __init__(self, *args, **kwargs):
        pass

    def tr(self, *args, **kwargs):
        pass


def _install_test_stubs():
    qtcore = types.ModuleType("PySide6.QtCore")
    qtcore.Qt = types.SimpleNamespace()
    qtcore.QObject = _DummyQObject
    qtcore.Signal = _DummySignal

    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QImage = _DummyQImage
    qtgui.QColor = _DummyQColor
    qtgui.QPainter = _DummyQPainter

    pyside6 = types.ModuleType("PySide6")
    pyside6.QtCore = qtcore
    pyside6.QtGui = qtgui

    pyfirmata2 = types.ModuleType("pyfirmata2")
    pyfirmata2.Board = type("Board", (), {})

    serial = types.ModuleType("serial")
    serial.Serial = object
    serial.tools = types.SimpleNamespace(
        list_ports=types.SimpleNamespace(comports=lambda: [])
    )

    sys.modules.setdefault("PySide6", pyside6)
    sys.modules.setdefault("PySide6.QtCore", qtcore)
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

from QMKataKeyboard import QMKataKeyboard


ROOT = Path(__file__).resolve().parent


class _FakeKeyboard:
    class keyboardModel:
        MCU = (None, None, "le")

    def __init__(self):
        self.keyboardModel = self.keyboardModel()
        self.module_calls = []

    def keyb_set_module(self, slot_id, binary):
        self.module_calls.append(("set", slot_id, binary))
        return True

    def keyb_del_module(self, slot_id):
        self.module_calls.append(("del", slot_id))
        return True


class _FakeModuleBuild:
    instances = []

    def __init__(self, toolchain, mapfile=None, firmware_path=None):
        self.toolchain = toolchain
        self.mapfile = mapfile
        self.firmware_path = firmware_path
        self.build_calls = []
        _FakeModuleBuild.instances.append(self)

    def build(self, source_file):
        self.build_calls.append(source_file)
        return {"binary": b"BIN", "hooks": ["combo_should_trigger"], "size": 3}


class KeybScriptModuleHelpersTest(unittest.TestCase):
    def setUp(self):
        self._orig_module = sys.modules.get("ModuleBuild")
        fake_module = types.ModuleType("ModuleBuild")
        fake_module.ModuleBuild = _FakeModuleBuild
        sys.modules["ModuleBuild"] = fake_module
        _FakeModuleBuild.instances.clear()

    def tearDown(self):
        if self._orig_module is None:
            sys.modules.pop("ModuleBuild", None)
        else:
            sys.modules["ModuleBuild"] = self._orig_module

    def _env(self):
        env = QMKataKeyboard.KeybScriptEnv(_FakeKeyboard(), firmware_path=str(ROOT))
        env.toolchain = object()
        env.mapfile = object()
        return env

    def test_build_module_uses_cached_builder_and_repo_root_relative_paths(self):
        env = self._env()

        first = env.build_module("module_examples/combo_layer_filter.c")
        second = env.build_module("module_examples/combo_layer_filter.c")

        self.assertEqual(first["binary"], b"BIN")
        self.assertEqual(second["binary"], b"BIN")
        self.assertEqual(1, len(_FakeModuleBuild.instances))
        self.assertIs(env._module_builder(), _FakeModuleBuild.instances[0])
        self.assertEqual(env.toolchain, _FakeModuleBuild.instances[0].toolchain)
        self.assertEqual(env.mapfile, _FakeModuleBuild.instances[0].mapfile)
        self.assertEqual(str(ROOT), _FakeModuleBuild.instances[0].firmware_path)
        self.assertEqual(
            [
                str(ROOT / "module_examples/combo_layer_filter.c"),
                str(ROOT / "module_examples/combo_layer_filter.c"),
            ],
            _FakeModuleBuild.instances[0].build_calls,
        )

    def test_build_module_preserves_absolute_paths(self):
        env = self._env()
        source = str(ROOT / "module_examples/combo_layer_filter.c")

        result = env.build_module(source)

        self.assertEqual(b"BIN", result["binary"])
        self.assertEqual([source], _FakeModuleBuild.instances[0].build_calls)

    def test_build_module_returns_none_without_toolchain(self):
        env = self._env()
        env.toolchain = None

        self.assertIsNone(env._module_builder())
        self.assertIsNone(env.build_module("module_examples/combo_layer_filter.c"))
        self.assertEqual([], _FakeModuleBuild.instances)

    def test_load_and_unload_module_forward_to_keyboard(self):
        env = self._env()

        self.assertTrue(env.load_module(4, {"binary": b"ABC"}))
        self.assertTrue(env.load_module(4, bytearray(b"DEF")))
        self.assertTrue(env.unload_module(4))

        self.assertEqual(
            [
                ("set", 4, b"ABC"),
                ("set", 4, bytearray(b"DEF")),
                ("del", 4),
            ],
            env.keyboard.module_calls,
        )


if __name__ == "__main__":
    unittest.main()
