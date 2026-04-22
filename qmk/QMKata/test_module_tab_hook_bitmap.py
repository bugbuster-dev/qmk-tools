import struct
import sys
import types
import unittest
import zlib

from ModuleBuild import (
    MODULE_HEADER_MAGIC,
    MODULE_HEADER_VERSION,
    MODULE_HEADER_SIZE,
    MODULE_HOOK_MAX,
    MODULE_HOOK_TABLE_OFF,
    ModuleBuild,
)


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


class _FakeToolchain:
    pass


class ModuleTabHookBitmapTest(unittest.TestCase):
    def test_assemble_writes_lifecycle_offsets_from_hook_table(self):
        raw_bin = bytearray(MODULE_HEADER_SIZE + MODULE_HOOK_MAX * 4 + 16)
        struct.pack_into("<I", raw_bin, MODULE_HOOK_TABLE_OFF + (3 * 4), 0x44)
        struct.pack_into("<I", raw_bin, MODULE_HOOK_TABLE_OFF + (4 * 4), 0x88)

        builder = ModuleBuild(_FakeToolchain())

        result = builder._assemble(bytes(raw_bin))

        self.assertIsNotNone(result)
        self.assertEqual(MODULE_HEADER_MAGIC, struct.unpack_from("<I", result["binary"], 0)[0])
        self.assertEqual(MODULE_HEADER_VERSION, struct.unpack_from("<H", result["binary"], 4)[0])
        self.assertEqual(0x44, struct.unpack_from("<I", result["binary"], 20)[0])
        self.assertEqual(0x88, struct.unpack_from("<I", result["binary"], 24)[0])

    def test_prepare_binary_for_load_patches_selected_hook_bitmap(self):
        tab = ModuleTab.__new__(ModuleTab)
        tab.last_build_result = {
            "binary": bytes(MODULE_HEADER_SIZE),
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
        built_binary = bytearray(MODULE_HEADER_SIZE)
        struct.pack_into("<I", built_binary, 20, 0x44)
        struct.pack_into("<I", built_binary, 24, 0x88)

        tab = ModuleTab.__new__(ModuleTab)
        tab.last_build_result = {
            "binary": bytes(built_binary),
        }
        tab.hook_checkboxes = [
            ("combo_should_trigger", _FakeCheckBox(False)),
            ("init", _FakeCheckBox(False)),
            ("deinit", _FakeCheckBox(False)),
        ]

        binary = tab._prepare_binary_for_load()

        self.assertEqual(0x00000000, struct.unpack_from("<I", binary, 12)[0])
        self.assertEqual(0x00000000, struct.unpack_from("<I", binary, 20)[0])
        self.assertEqual(0x00000000, struct.unpack_from("<I", binary, 24)[0])

    def test_prepare_binary_for_load_preserves_checked_lifecycle_offsets(self):
        built_binary = bytearray(MODULE_HEADER_SIZE)
        struct.pack_into("<I", built_binary, 20, 0x44)
        struct.pack_into("<I", built_binary, 24, 0x88)

        tab = ModuleTab.__new__(ModuleTab)
        tab.last_build_result = {
            "binary": bytes(built_binary),
        }
        tab.hook_checkboxes = [
            ("init", _FakeCheckBox(True)),
            ("deinit", _FakeCheckBox(True)),
        ]

        binary = tab._prepare_binary_for_load()

        self.assertEqual(0x00000018, struct.unpack_from("<I", binary, 12)[0])
        self.assertEqual(0x00000044, struct.unpack_from("<I", binary, 20)[0])
        self.assertEqual(0x00000088, struct.unpack_from("<I", binary, 24)[0])

    def test_selected_hook_bitmap_maps_reserved_labels_to_reserved_bits(self):
        tab = ModuleTab.__new__(ModuleTab)
        tab.hook_checkboxes = [
            ("init", _FakeCheckBox(True)),
            ("deinit", _FakeCheckBox(True)),
            ("hook_5", _FakeCheckBox(False)),
        ]

        self.assertEqual(0x00000018, tab._selected_hook_bitmap())


def _recompute_crc(binary):
    """Reference CRC that must match validate_module_crc() in firmware:
    zlib.crc32 over the whole binary with the 4-byte crc32 field
    (last 4 bytes of the module header) held at zero."""
    buf = bytearray(binary)
    crc_off = MODULE_HEADER_SIZE - 4
    struct.pack_into("<I", buf, crc_off, 0)
    return zlib.crc32(bytes(buf)) & 0xFFFFFFFF


class ModuleCrcTest(unittest.TestCase):
    def test_assemble_writes_valid_crc_over_entire_binary(self):
        # A non-trivial body so the CRC depends on more than the header.
        body_size = MODULE_HOOK_MAX * 4 + 128
        raw_bin = bytearray(MODULE_HEADER_SIZE + body_size)
        for i in range(body_size):
            raw_bin[MODULE_HEADER_SIZE + i] = (i * 37 + 11) & 0xFF

        result = ModuleBuild(_FakeToolchain())._assemble(bytes(raw_bin))
        self.assertIsNotNone(result)
        binary = result["binary"]

        stored_crc = struct.unpack_from("<I", binary, MODULE_HEADER_SIZE - 4)[0]
        self.assertEqual(stored_crc, _recompute_crc(binary))

    def test_prepare_binary_for_load_keeps_crc_valid_after_bitmap_patch(self):
        # Simulate a post-build binary: assemble with body, then let the UI
        # flip hook selections, which rewrites hook_bitmap/init/deinit.
        raw_bin = bytearray(MODULE_HEADER_SIZE + MODULE_HOOK_MAX * 4 + 64)
        struct.pack_into("<I", raw_bin, MODULE_HOOK_TABLE_OFF + (3 * 4), 0x44)
        struct.pack_into("<I", raw_bin, MODULE_HOOK_TABLE_OFF + (4 * 4), 0x88)
        # Fill body with arbitrary bytes so CRC is sensitive to content.
        for i in range(64):
            raw_bin[MODULE_HEADER_SIZE + MODULE_HOOK_MAX * 4 + i] = (i ^ 0x5A) & 0xFF

        built = ModuleBuild(_FakeToolchain())._assemble(bytes(raw_bin))
        self.assertIsNotNone(built)

        tab = ModuleTab.__new__(ModuleTab)
        tab.last_build_result = built
        # Deselect init/deinit so _prepare_binary_for_load must zero
        # offsets 20 and 24, exercising the CRC-invalidation path.
        tab.hook_checkboxes = [
            ("combo_should_trigger", _FakeCheckBox(True)),
            ("init", _FakeCheckBox(False)),
            ("deinit", _FakeCheckBox(False)),
        ]
        tab.log = lambda _message: None

        prepared = tab._prepare_binary_for_load()

        stored_crc = struct.unpack_from("<I", prepared, MODULE_HEADER_SIZE - 4)[0]
        self.assertEqual(stored_crc, _recompute_crc(prepared))
        # Sanity: bytes actually changed relative to the built binary, so
        # the CRC had to be recomputed (not just copied forward).
        self.assertNotEqual(bytes(built["binary"]), bytes(prepared))


if __name__ == "__main__":
    unittest.main()
