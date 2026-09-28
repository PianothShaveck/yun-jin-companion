# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows process, taskbar icons and shortcut identity via public Shell APIs."""
import ctypes as C
import sys
import uuid
from pathlib import Path

APP_ID = 'pianoth.yunjin.desktoppet.v1'


def set_process_identity():
    """Run before importing Qt; verify instead of silently ignoring a Shell error."""
    if sys.platform != 'win32':
        return False
    shell = C.windll.shell32
    shell.SetCurrentProcessExplicitAppUserModelID.argtypes = [C.c_wchar_p]
    shell.SetCurrentProcessExplicitAppUserModelID.restype = C.c_long
    result = shell.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    if result < 0:
        raise OSError('SetCurrentProcessExplicitAppUserModelID: 0x%08X' % (result & 0xffffffff))
    shell.GetCurrentProcessExplicitAppUserModelID.argtypes = [C.POINTER(C.c_void_p)]
    shell.GetCurrentProcessExplicitAppUserModelID.restype = C.c_long
    ole = C.windll.ole32
    ole.CoTaskMemFree.argtypes = [C.c_void_p]
    ole.CoTaskMemFree.restype = None
    identity = C.c_void_p()
    try:
        result = shell.GetCurrentProcessExplicitAppUserModelID(C.byref(identity))
        if result < 0 or not identity.value or C.wstring_at(identity.value) != APP_ID:
            raise OSError('Windows did not retain the Yun Jin application identity')
    finally:
        if identity.value:
            ole.CoTaskMemFree(identity)
    return True


def install_taskbar_icons(app, icon_path):
    """Set native small/large icons on every Qt top-level HWND, including dialogs.

    Keep HICONs alive for the process lifetime. Qt can recreate a native window;
    the event filter applies the same icons to its replacement handle as well.
    """
    if sys.platform != 'win32':
        return None
    import atexit
    import logging
    from ctypes import wintypes as W
    from PyQt6.QtCore import QObject, QEvent, Qt
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QWidget

    path = str(Path(icon_path).resolve(strict=True))
    icon = QIcon(path)
    if icon.isNull():
        raise OSError('Cannot read the Yun Jin taskbar icon: ' + path)
    app.setWindowIcon(icon)
    user = C.WinDLL('user32', use_last_error=True)
    user.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, C.c_int, C.c_int, W.UINT]
    user.LoadImageW.restype = W.HANDLE
    user.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.SendMessageW.restype = W.LPARAM
    user.GetSystemMetrics.argtypes = [C.c_int]
    user.GetSystemMetrics.restype = C.c_int
    user.DestroyIcon.argtypes = [W.HANDLE]
    user.DestroyIcon.restype = W.BOOL
    handles = []
    try:
        for width_metric, height_metric in ((49, 50), (11, 12)):
            handle = user.LoadImageW(None, path, 1, user.GetSystemMetrics(width_metric),
                                     user.GetSystemMetrics(height_metric), 0x10)
            if not handle:
                raise C.WinError(C.get_last_error())
            handles.append(handle)
    except Exception:
        for handle in handles:
            user.DestroyIcon(handle)
        raise

    class TaskbarIcons(QObject):
        def __init__(self):
            super().__init__(app)
            self.busy = False
            self.handles = handles

        def apply(self, widget, hwnd=None):
            if self.busy:
                return
            self.busy = True
            try:
                widget.setWindowIcon(icon)
                hwnd = hwnd or int(widget.winId())
                for kind, handle in enumerate(handles):
                    user.SendMessageW(hwnd, 0x0080, kind, handle)  # WM_SETICON
                    if user.SendMessageW(hwnd, 0x007F, kind, 0) != handle:  # WM_GETICON
                        raise OSError('Windows did not retain the Yun Jin window icon')
            finally:
                self.busy = False

        def eventFilter(self, obj, event):
            if not self.busy and isinstance(obj, QWidget) and obj.isWindow():
                try:
                    if event.type() == QEvent.Type.Show:
                        self.apply(obj)
                    elif event.type() in (QEvent.Type.WinIdChange, QEvent.Type.WindowIconChange) and obj.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
                        hwnd = obj.effectiveWinId()
                        if hwnd:
                            self.apply(obj, int(hwnd))
                except Exception:
                    logging.exception('Cannot apply Yun Jin native taskbar icon')
            return False

    controller = TaskbarIcons()
    app.installEventFilter(controller)
    app._yun_jin_taskbar_icons = controller
    # At interpreter shutdown no live window will continue using these handles.
    atexit.register(lambda: [user.DestroyIcon(handle) for handle in handles])
    return controller


def stamp_shortcut(path):
    """Persist and read back the same AppUserModelID used by the GUI process."""
    if sys.platform != 'win32':
        raise OSError('Windows Shell is required')
    from ctypes import wintypes as W

    class GUID(C.Structure):
        _fields_ = [('data', C.c_ubyte * 16)]
        def __init__(self, value):
            super().__init__()
            self.data[:] = uuid.UUID(value).bytes_le

    class KEY(C.Structure):
        _fields_ = [('fmtid', GUID), ('pid', W.DWORD)]

    class VALUE(C.Union):
        _fields_ = [('text', C.c_void_p), ('storage', C.c_void_p * 2), ('alignment', C.c_ulonglong)]

    class PROPVARIANT(C.Structure):
        _fields_ = [('vt', W.WORD), ('r1', W.WORD), ('r2', W.WORD), ('r3', W.WORD), ('value', VALUE)]

    def check(hr):
        if hr < 0:
            raise OSError('Windows Shell error 0x%08X' % (hr & 0xffffffff))

    ole = C.OleDLL('ole32')
    shell = C.WinDLL('shell32')
    ole.CoInitializeEx.argtypes = [C.c_void_p, W.DWORD]
    ole.CoInitializeEx.restype = C.c_long
    result = ole.CoInitializeEx(None, 2)
    check(result)
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    ole.PropVariantClear.argtypes = [C.POINTER(PROPVARIANT)]
    ole.PropVariantClear.restype = C.c_long
    shell.SHGetPropertyStoreFromParsingName.argtypes = [W.LPCWSTR, C.c_void_p, W.DWORD, C.POINTER(GUID), C.POINTER(C.c_void_p)]
    shell.SHGetPropertyStoreFromParsingName.restype = C.c_long
    iid = GUID('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
    key = KEY(GUID('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'), 5)

    def method(store, slot, result_type, *types):
        table = C.cast(store, C.POINTER(C.POINTER(C.c_void_p))).contents
        return C.WINFUNCTYPE(result_type, C.c_void_p, *types)(table[slot])

    def open_store(flags):
        store = C.c_void_p()
        check(shell.SHGetPropertyStoreFromParsingName(str(Path(path).resolve()), None, flags, C.byref(iid), C.byref(store)))
        return store

    def release(store):
        method(store, 2, W.ULONG)(store)

    try:
        store = open_store(2)  # GPS_READWRITE
        try:
            buffer = C.create_unicode_buffer(APP_ID)
            value = PROPVARIANT()
            value.vt = 31  # VT_LPWSTR; buffer is owned by Python, not COM.
            value.value.text = C.cast(buffer, C.c_void_p).value
            check(method(store, 6, C.c_long, C.POINTER(KEY), C.POINTER(PROPVARIANT))(store, C.byref(key), C.byref(value)))
            check(method(store, 7, C.c_long)(store))
        finally:
            release(store)
        # Reopen to verify persistence on disk, not just the in-memory value.
        store = open_store(0)
        try:
            value = PROPVARIANT()
            try:
                check(method(store, 5, C.c_long, C.POINTER(KEY), C.POINTER(PROPVARIANT))(store, C.byref(key), C.byref(value)))
                if value.vt != 31 or not value.value.text or C.wstring_at(value.value.text) != APP_ID:
                    raise RuntimeError('Shortcut AppUserModelID was not saved')
            finally:
                ole.PropVariantClear(C.byref(value))
        finally:
            release(store)
    finally:
        ole.CoUninitialize()


def install_shortcut_identity():
    from ctypes import wintypes as W
    shell = C.WinDLL('shell32')
    shell.SHGetFolderPathW.argtypes = [W.HWND, C.c_int, W.HANDLE, W.DWORD, W.LPWSTR]
    shell.SHGetFolderPathW.restype = C.c_long
    for folder in (0x10, 0x02):  # Desktop directory, current user's Start/Programs.
        buffer = C.create_unicode_buffer(260)
        hr = shell.SHGetFolderPathW(None, folder, None, 0, buffer)
        if hr < 0:
            raise OSError('Cannot locate shortcut folder')
        stamp_shortcut(Path(buffer.value) / 'Yun Jin Companion.lnk')
    print('Identita Windows dei collegamenti verificata.')


if __name__ == '__main__':
    install_shortcut_identity()
