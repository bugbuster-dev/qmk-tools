import win32con
import ctypes
import ctypes.wintypes
import threading

from PySide6.QtCore import Qt, QThread, Signal

#-------------------------------------------------------------------------------
# window focus listener code from:
# https://gist.github.com/keturn/6695625
#
class WinFocusListener(QThread):
    winfocus_signal = Signal(str)

    def __init__(self):
        super().__init__()

        self.native_tid = None
        self.user32 = ctypes.windll.user32
        self.ole32 = ctypes.windll.ole32
        self.kernel32 = ctypes.windll.kernel32

        self.WinEventProcType = ctypes.WINFUNCTYPE(
            None,
            ctypes.wintypes.HANDLE,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LONG,
            ctypes.wintypes.LONG,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD
        )

        # The types of events we want to listen for, and the names we'll use for
        # them in the log output. Pick from
        # http://msdn.microsoft.com/en-us/library/windows/desktop/dd318066(v=vs.85).aspx
        self.eventTypes = {
            win32con.EVENT_SYSTEM_FOREGROUND: "Foreground",
        #    win32con.EVENT_OBJECT_FOCUS: "Focus",
        #    win32con.EVENT_OBJECT_SHOW: "Show",
        #    win32con.EVENT_SYSTEM_DIALOGSTART: "Dialog",
        #    win32con.EVENT_SYSTEM_CAPTURESTART: "Capture",
        #    win32con.EVENT_SYSTEM_MINIMIZEEND: "UnMinimize"
        }

        # limited information would be sufficient, but our platform doesn't have it.
        self.processFlag = getattr(win32con, 'PROCESS_QUERY_LIMITED_INFORMATION',
                              win32con.PROCESS_QUERY_INFORMATION)

        self.threadFlag = getattr(win32con, 'THREAD_QUERY_LIMITED_INFORMATION',
                             win32con.THREAD_QUERY_INFORMATION)

        self.lastTime = 0

    def log(self, msg):
        #print(msg)
        self.winfocus_signal.emit(msg)

    def logError(self, msg):
        sys.stdout.write(msg + '\n')

    def getProcessID(self, dwEventThread, hwnd):
        # It's possible to have a window we can get a PID out of when the thread
        # isn't accessible, but it's also possible to get called with no window,
        # so we have two approaches.

        hThread = self.kernel32.OpenThread(self.threadFlag, 0, dwEventThread)

        if hThread:
            try:
                processID = self.kernel32.GetProcessIdOfThread(hThread)
                if not processID:
                    self.logError("Couldn't get process for thread %s: %s" %
                             (hThread, ctypes.WinError()))
            finally:
                self.kernel32.CloseHandle(hThread)
        else:
            errors = ["No thread handle for %s: %s" %
                      (dwEventThread, ctypes.WinError(),)]

            if hwnd:
                processID = ctypes.wintypes.DWORD()
                threadID = self.user32.GetWindowThreadProcessId(
                    hwnd, ctypes.byref(processID))
                if threadID != dwEventThread:
                    self.logError("Window thread != event thread? %s != %s" %
                             (threadID, dwEventThread))
                if processID:
                    processID = processID.value
                else:
                    errors.append(
                        "GetWindowThreadProcessID(%s) didn't work either: %s" % (
                        hwnd, ctypes.WinError()))
                    processID = None
            else:
                processID = None

            if not processID:
                for err in errors:
                    self.logError(err)

        return processID

    def getProcessFilename(self, processID):
        hProcess = self.kernel32.OpenProcess(self.processFlag, 0, processID)
        if not hProcess:
            self.logError("OpenProcess(%s) failed: %s" % (processID, ctypes.WinError()))
            return None

        try:
            filenameBufferSize = ctypes.wintypes.DWORD(4096)
            filename = ctypes.create_unicode_buffer(filenameBufferSize.value)
            self.kernel32.QueryFullProcessImageNameW(hProcess, 0, ctypes.byref(filename),
                                                ctypes.byref(filenameBufferSize))

            return filename.value
        finally:
            self.kernel32.CloseHandle(hProcess)

    def callback(self, hWinEventHook, event, hwnd, idObject, idChild, dwEventThread,
                 dwmsEventTime):

        length = self.user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(hwnd, title, length + 1)

        processID = self.getProcessID(dwEventThread, hwnd)

        shortName = '?'
        if processID:
            filename = self.getProcessFilename(processID)
            if filename:
                shortName = '\\'.join(filename.rsplit('\\', 2)[-2:])

        if hwnd:
            hwnd = hex(hwnd)
        elif idObject == win32con.OBJID_CURSOR:
            hwnd = '<Cursor>'

        #self.log(u"%s:%04.2f\t%-10s\t"
            #u"W:%-8s\tP:%-8d\tT:%-8d\t"
            #u"%s\t%s" % (
            #dwmsEventTime, float(dwmsEventTime - self.lastTime)/1000, self.eventTypes.get(event, hex(event)),
            #hwnd, processID or -1, dwEventThread or -1,
            #shortName, title.value))
        self.log(u"P:%-8d\t%s\t%s" % (processID or -1, shortName, title.value))
        self.lastTime = dwmsEventTime

    def setHook(self, WinEventProc, eventType):
        return self.user32.SetWinEventHook(
            eventType,
            eventType,
            0,
            WinEventProc,
            0,
            0,
            win32con.WINEVENT_OUTOFCONTEXT
        )

    def run(self):
        self.native_tid = threading.get_native_id()

        self.ole32.CoInitialize(0)
        WinEventProc = self.WinEventProcType(self.callback)
        self.user32.SetWinEventHook.restype = ctypes.wintypes.HANDLE

        hookIDs = [self.setHook(WinEventProc, et) for et in self.eventTypes.keys()]
        msg = ctypes.wintypes.MSG()
        while True:
            ret = self.user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            #print(f"GetMessageW:{ret}")
            if ret > 0:
                self.user32.TranslateMessageW(msg)
                self.user32.DispatchMessageW(msg)
            elif ret <= 0:
                break

        for hookID in hookIDs:
            self.user32.UnhookWinEvent(hookID)
        self.ole32.CoUninitialize()
        print("WinFocusListener thread stopped")

    def stop(self):
        self.user32.PostThreadMessageW(self.native_tid, win32con.WM_QUIT, 0, 0)
        self.wait()
