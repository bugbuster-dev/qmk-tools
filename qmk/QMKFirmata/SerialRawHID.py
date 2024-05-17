import serial
import hid

from DebugTracer import DebugTracer

# todo move to separate file
class SerialRawHID(serial.SerialBase):
    FIRMATA_MSG         = 0xFA
    QMK_RAW_USAGE_PAGE  = 0xFF60
    QMK_RAW_USAGE_ID    = 0x61

    def __init__(self, vid, pid, epsize=64, timeout=100):
        self.dbg = DebugTracer(print=1, trace=1, obj=self)
        self.vid = vid
        self.pid = pid
        self.epsize = epsize
        self.timeout = timeout
        self.hid_device = None
        self._port = "{:04x}:{:04x}".format(vid, pid)
        self.open()

    def _reconfigure_port(self):
        pass

    def __str__(self) -> str:
        return "RAWHID: vid={:04x}, pid={:04x}".format(self.vid, self.pid)

    def _read_msg(self):
        try:
            data = bytearray(self.hid_device.read(self.epsize, self.timeout))
            # todo may strip trailing zeroes after END_SYSEX
            #data = data.rstrip(bytearray([0])) # remove trailing zeros
            #if len(data) > 0:
                #self.dbg.tr(f"rawhid read:{data.hex(' ')}")
        except Exception as e:
            data = bytearray()

        if len(data) == 0:
            #self.data.append(0) # dummy data to feed firmata
            return

        if data[0] == self.FIRMATA_MSG:
            data.pop(0)
        self.data.extend(data)

    def inWaiting(self):
        if len(self.data) == 0:
            self._read_msg()
        return len(self.data)

    def open(self):
        try:
            device_list = hid.enumerate(self.vid, self.pid)
            device = None
            for _device in device_list:
                #self.dbg.tr(f"found hid device: {_device}")
                if _device['usage_page'] == self.QMK_RAW_USAGE_PAGE: # 'usage' should be QMK_RAW_USAGE_ID
                    self.dbg.tr(f"found qmk raw hid device: {_device}")
                    device = _device
                    break

            if not device:
                raise Exception("no raw hid device found")

            self.hid_device = hid.device()
            self.hid_device.open_path(device['path'])

            self.data = bytearray()
            self.write(bytearray([0x00, self.FIRMATA_MSG, 0xf0, 0x71, 0xf7]))
            #self._read_msg()
            #if len(self.data) == 0:
                #self.dbg.tr(f"no response from device")
        except Exception as e:
            self.hid_device = None
            raise serial.SerialException(f"Could not open HID device: {e}")

        self.dbg.tr(f"opened HID device: {self.hid_device}")

    def is_open(self):
        return self.hid_device != None

    def close(self):
        if self.hid_device:
            self.hid_device.close()
            self.hid_device = None

    def write(self, data):
        if not self.hid_device:
            raise serial.SerialException("device not open")

        data = bytearray([0x00, self.FIRMATA_MSG]) + data
        #print(f"rawhid write:{data.hex(' ')}")
        return self.hid_device.write(data)

    def read(self, size=1):
        if not self.hid_device:
            raise serial.SerialException("device not open")

        if len(self.data) == 0:
            self._read_msg()
        if len(self.data) > 0:
            #self.dbg.tr(f"read:{self.data[0]}")
            return chr(self.data.pop(0))

        self.dbg.tr(f"read: no data")
        return chr(0)

    def read_all(self):
        pass

    def read_until(self, expected=b'\n', size=None):
        pass
