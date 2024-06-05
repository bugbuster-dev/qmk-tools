import serial, hid, time
from DebugTracer import DebugTracer

class SerialRawHID(serial.SerialBase):
    FIRMATA_MSG         = 0xFA
    QMK_RAW_USAGE_PAGE  = 0xFF60
    QMK_RAW_USAGE_ID    = 0x61

    def __init__(self, vid, pid, epsize=64, timeout=100):
        #region debug tracers
        self.dbg = DebugTracer(zones={
            'D': 0,
            'WRITE': 1,
            'READ': 0,
        }, obj=self)
        self.dbg_write = None # self.dbg
        self.dbg_read = None
        #regionend

        self.vid = vid
        self.pid = pid
        self.epsize = epsize
        self.timeout = timeout
        self.hid_device = None
        self._port = "{:04x}:{:04x}".format(vid, pid)
        self.MAX_DATA_SIZE = epsize-2
        self.open()
        self.num_read_errors = 0 # device detached if too many read errors
        self.try_reopen = False

    def _reconfigure_port(self):
        pass

    def __str__(self) -> str:
        return "RAWHID: vid={:04x}, pid={:04x}".format(self.vid, self.pid)

    def _read_msg(self):
        if not self.hid_device:
            return
        try:
            data = bytearray(self.hid_device.read(self.epsize, self.timeout))
            self.num_read_errors = 0
            # todo may strip trailing zeroes after END_SYSEX
            #data = data.rstrip(bytearray([0])) # remove trailing zeros
            #if len(data) > 0:
                #self.dbg.tr('READ', f"rawhid read:{data.hex(' ')}")
        except Exception as e:
            #self.dbg.tr('E', "{}", e)
            data = None
            self.num_read_errors += 1
            time.sleep(0.1)

        if self.num_read_errors > 10:
            self.dbg.tr('E', "too many read errors, closing device")
            self.close()
            self.try_reopen = True

        if not data or len(data) == 0:
            return

        if data[0] == self.FIRMATA_MSG:
            data.pop(0)
        self.data.extend(data)

    def inWaiting(self):
        if len(self.data) == 0:
            self._read_msg()
        return len(self.data)

    def _reopen(self):
        if self.try_reopen:
            try:
                self.open()
            except Exception as e:
                pass
            if self.hid_device:
                self.num_read_errors = 0
                self.try_reopen = False
            else:
                time.sleep(0.2)

    def open(self):
        try:
            device = None
            device_list = hid.enumerate(self.vid, self.pid)
            for _device in device_list:
                if _device['usage_page'] == self.QMK_RAW_USAGE_PAGE: # 'usage' should be QMK_RAW_USAGE_ID
                    self.dbg.tr('I', f"found qmk raw hid device: {_device}")
                    device = _device
                    break

            if not device:
                raise Exception("no raw hid device found")

            self.hid_device = hid.device()
            self.hid_device.open_path(device['path'])

            self.data = bytearray()
            self.write(bytearray([0xf0, 0x71, 0xf7]))
            #self._read_msg()
            #if len(self.data) == 0:
                #self.dbg.tr('READ', f"no response from device")
        except Exception as e:
            self.hid_device = None
            raise serial.SerialException(f"Could not open HID device: {e}")

        self.dbg.tr('I', f"opened HID device: {self.hid_device}")

    def is_open(self):
        return self.hid_device != None

    def close(self):
        if self.hid_device:
            self.hid_device.close()
            self.hid_device = None

    def write(self, data):
        if not self.hid_device:
            self._reopen()

        if not self.hid_device:
            raise serial.SerialException("device not open")

        # todo: span sysex data over multiple epsized packets
        if len(data) > self.MAX_DATA_SIZE:
            self.dbg.tr('E', f"data too large: {len(data)}")
            raise serial.SerialException("data too large")

        total_sent = 0
        while len(data) > 0:
            chunk = bytearray([0x00, self.FIRMATA_MSG]) + data[:self.MAX_DATA_SIZE]
            data = data[self.MAX_DATA_SIZE:]
            self.hid_device.write(chunk)
            total_sent += len(chunk)
            if self.dbg_write: self.dbg_write.tr('WRITE', f"write: {chunk.hex(' ')}")
        if self.dbg_write:
            self.dbg_write.tr('WRITE', f"total sent: {total_sent}")
        return total_sent

    def read(self):
        if not self.hid_device:
            self._reopen()

        if not self.hid_device:
            raise serial.SerialException("device not open")

        if len(self.data) == 0:
            self._read_msg()
        if len(self.data) > 0:
            if self.dbg_read: self.dbg_read.tr('READ', f"read:{self.data[0]}")
            return chr(self.data.pop(0))

        if self.dbg_read: self.dbg_read.tr('READ', f"read: no data")
        return chr(0)

    def read_all(self):
        raise serial.SerialException("read_all: not implemented")

    def read_until(self, expected=b'\n', size=None):
        raise serial.SerialException("read_until: not implemented")
