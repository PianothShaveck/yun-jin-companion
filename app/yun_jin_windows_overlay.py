# SPDX-License-Identifier: GPL-3.0-or-later
"""Restore the pet's Windows Z order without activating it or moving focus."""
import ctypes as C
from ctypes import wintypes as W
import logging
import os
import sys
from PyQt6 import sip
from PyQt6.QtCore import QObject, QEvent, QTimer, Qt

HWND_TOPMOST = -1
WS_EX_TOPMOST = 0x00000008
GWL_EXSTYLE = -20
GW_HWNDPREV = 3
POSITION_FLAGS = 0x0001 | 0x0002 | 0x0010 | 0x0200  # size, move, activate, owner unchanged
EVENT_SYSTEM_FOREGROUND = 0x0003
PREFERENCE = 'windows_fullscreen_overlay'
LABEL = 'Mostra anche sopra le app a schermo intero'
GWL_STYLE = -16
WS_CAPTION = 0x00c00000


class MonitorInfo(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT), ('dwFlags', W.DWORD)]


class NativeTopmost:
    def __init__(self, user=None):
        self.user = user if user is not None else C.WinDLL('user32', use_last_error=True)
        self.hook = None
        self.callback = None
        self.get_style = getattr(self.user, 'GetWindowLongPtrW', self.user.GetWindowLongW)
        signatures = (
            (self.user.GetForegroundWindow, [], W.HWND),
            (self.user.GetShellWindow, [], W.HWND),
            (self.user.GetDesktopWindow, [], W.HWND),
            (self.user.GetWindow, [W.HWND, W.UINT], W.HWND),
            (self.user.GetWindowThreadProcessId, [W.HWND, C.POINTER(W.DWORD)], W.DWORD),
            (self.user.IsWindowVisible, [W.HWND], W.BOOL),
            (self.user.IsIconic, [W.HWND], W.BOOL),
            (self.user.GetWindowRect, [W.HWND, C.POINTER(W.RECT)], W.BOOL),
            (self.user.MonitorFromWindow, [W.HWND, W.DWORD], W.HANDLE),
            (self.user.GetMonitorInfoW, [W.HANDLE, C.POINTER(MonitorInfo)], W.BOOL),
            (self.get_style, [W.HWND, C.c_int], C.c_ssize_t),
            (self.user.SetWindowPos, [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT], W.BOOL),
            (self.user.UnhookWinEvent, [W.HANDLE], W.BOOL),
        )
        for function, args, result in signatures:
            function.argtypes = args
            function.restype = result

    def watch(self, changed):
        # OUTOFCONTEXT: notifications arrive on Qt's GUI thread; no DLL injection.
        callback_type = C.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND,
                                     W.LONG, W.LONG, W.DWORD, W.DWORD)

        def callback(*_):
            if self.hook:
                changed()

        self.callback = callback_type(callback)
        function = self.user.SetWinEventHook
        function.argtypes = [W.DWORD, W.DWORD, W.HMODULE, callback_type,
                             W.DWORD, W.DWORD, W.DWORD]
        function.restype = W.HANDLE
        self.hook = function(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
                             None, self.callback, 0, 0, 0x0002)  # SKIPOWNPROCESS
        # A missing hook is harmless: the low-frequency check remains active.

    def fullscreen(self, hwnd):
        """A foreign, borderless foreground window covering the pet's monitor."""
        user = self.user
        foreground = user.GetForegroundWindow()
        if not foreground or foreground == hwnd or not user.IsWindowVisible(foreground) or user.IsIconic(foreground):
            return False
        if foreground in (user.GetShellWindow(), user.GetDesktopWindow()):
            return False
        pid = W.DWORD()
        if not user.GetWindowThreadProcessId(foreground, C.byref(pid)) or pid.value == os.getpid():
            return False
        if self.get_style(foreground, GWL_STYLE) & WS_CAPTION:
            return False
        monitor = user.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        info = MonitorInfo(); info.cbSize = C.sizeof(info)
        rect = W.RECT()
        if not monitor or not user.GetMonitorInfoW(monitor, C.byref(info)) or not user.GetWindowRect(foreground, C.byref(rect)):
            return False
        bounds = info.rcMonitor
        return (rect.left <= bounds.left + 1 and rect.top <= bounds.top + 1
                and rect.right >= bounds.right - 1 and rect.bottom >= bounds.bottom - 1)

    def restore(self, hwnd):
        user = self.user
        if not user.IsWindowVisible(hwnd) or user.IsIconic(hwnd):
            return False
        foreground = user.GetForegroundWindow()
        if not foreground or foreground == hwnd:
            return False
        pid = W.DWORD()
        if not user.GetWindowThreadProcessId(foreground, C.byref(pid)) or pid.value == os.getpid():
            return False  # Preserve Yun Jin menus, panels and modal dialogs.
        if not user.IsWindowVisible(foreground) or user.IsIconic(foreground):
            return False
        needs_restore = not (self.get_style(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)
        if not needs_restore:
            pet_rect, front_rect = W.RECT(), W.RECT()
            if not user.GetWindowRect(hwnd, C.byref(pet_rect)) or not user.GetWindowRect(foreground, C.byref(front_rect)):
                return False
            if (pet_rect.right <= front_rect.left or front_rect.right <= pet_rect.left
                    or pet_rect.bottom <= front_rect.top or front_rect.bottom <= pet_rect.top):
                return False
            # A second topmost window (often a borderless game) can cover the pet
            # while WS_EX_TOPMOST is still set. Check order, not just that flag.
            previous = user.GetWindow(hwnd, GW_HWNDPREV)
            seen = set()
            for _ in range(512):
                if not previous or previous in seen:
                    break
                if previous == foreground:
                    needs_restore = True
                    break
                seen.add(previous)
                previous = user.GetWindow(previous, GW_HWNDPREV)
        if not needs_restore:
            return False
        if not user.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, POSITION_FLAGS):
            raise OSError('Unable to restore Yun Jin topmost window')
        return True

    def close(self):
        if self.hook:
            self.user.UnhookWinEvent(self.hook)
            self.hook = None
        # Keep the callback alive until this backend is disposed.


class WindowsOverlay(QObject):
    def __init__(self, app, pet, native=None):
        super().__init__(app)
        self.pet = pet
        self.closed = False
        self.failed = False
        store = getattr(pet, 'store', None)
        self.enabled = bool(store.preference(PREFERENCE, True)) if store is not None else True
        self.native = native if native is not None else NativeTopmost()
        self.pending = QTimer(self)
        self.pending.setSingleShot(True)
        self.pending.setInterval(100)
        self.pending.timeout.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.CoarseTimer)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        try:
            self.native.watch(self.request)
        except Exception:
            logging.exception('Unable to watch Windows foreground changes')
        pet.installEventFilter(self)
        pet.destroyed.connect(self.close)
        app.aboutToQuit.connect(self.close)
        self.sync_visibility()

    def visible(self):
        return (not self.closed and not sip.isdeleted(self.pet)
                and not getattr(self.pet, 'closing', False)
                and not getattr(self.pet, 'character_hidden', False)
                and (self.pet.isVisible() or getattr(self.pet, 'fullscreen_hidden', False))
                and not self.pet.isMinimized())

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if self.enabled and not sip.isdeleted(self.pet):
            self.pet.set_fullscreen_hidden(False)
        self.sync_visibility()
        self.refresh()

    def sync_visibility(self):
        if self.visible():
            if not self.timer.isActive():
                self.timer.start()
            self.request()
        else:
            self.timer.stop()
            self.pending.stop()

    def request(self):
        if self.visible() and not self.pending.isActive():
            self.pending.start()

    def refresh(self):
        if not self.visible():
            self.sync_visibility()
            return
        if not self.pet.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
            return
        hwnd = self.pet.effectiveWinId()
        if not hwnd:
            return
        try:
            hidden = not self.enabled and self.native.fullscreen(int(hwnd))
            setter = getattr(self.pet, 'set_fullscreen_hidden', None)
            if setter is not None:
                setter(hidden)
            if hidden:
                self.failed = False
                return
            self.native.restore(int(hwnd))
            self.failed = False
        except Exception:
            if not self.failed:
                logging.exception('Unable to maintain Yun Jin Windows overlay')
            self.failed = True

    def eventFilter(self, obj, event):
        if obj is self.pet and event.type() in (QEvent.Type.Show, QEvent.Type.Hide,
                                                QEvent.Type.WindowStateChange, QEvent.Type.WinIdChange):
            self.sync_visibility()
        return False

    def close(self, *_):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        self.pending.stop()
        self.native.close()


def install_windows_overlay(app, pet):
    if sys.platform != 'win32' or app.platformName() != 'windows':
        return None
    return WindowsOverlay(app, pet)
