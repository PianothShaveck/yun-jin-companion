# SPDX-License-Identifier: GPL-3.0-or-later
"""macOS fullscreen overlay using public AppKit APIs and Qt-owned NSPanels."""
import ctypes
import logging
import weakref
from PyQt6 import sip
from PyQt6.QtCore import QObject, QEvent, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget, QDialog, QMenu, QMessageBox, QFileDialog

PREFERENCE = 'mac_fullscreen_overlay'
LABEL = 'Mostra anche sopra le app a schermo intero'
# NSWindowCollectionBehavior values from the AppKit SDK.
JOIN_SPACES = 1
MOVE_TO_ACTIVE_SPACE = 2
FULLSCREEN_PRIMARY = 128
FULLSCREEN_AUXILIARY = 256
FULLSCREEN_NONE = 512
PRIMARY = 1 << 16
AUXILIARY = 1 << 17
JOIN_APPLICATIONS = 1 << 18
NONACTIVATING_PANEL = 1 << 7


def overlay_behavior(previous):
    return ((previous & ~(MOVE_TO_ACTIVE_SPACE | FULLSCREEN_PRIMARY | FULLSCREEN_NONE |
                           PRIMARY | AUXILIARY)) |
            JOIN_SPACES | FULLSCREEN_AUXILIARY | JOIN_APPLICATIONS)


class AppKit:
    def __init__(self):
        self.framework = ctypes.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
        self.objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
        self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self.objc.objc_getClass.restype = ctypes.c_void_p
        self.objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self.objc.sel_registerName.restype = ctypes.c_void_p
        self.address = ctypes.cast(self.objc.objc_msgSend, ctypes.c_void_p).value
        self.application = self.send(self.cls('NSApplication'), 'sharedApplication')

    def cls(self, name):
        return self.objc.objc_getClass(name.encode())

    def send(self, receiver, selector, result=ctypes.c_void_p, types=(), args=()):
        fn = ctypes.CFUNCTYPE(result, ctypes.c_void_p, ctypes.c_void_p, *types)(self.address)
        return fn(receiver, self.objc.sel_registerName(selector.encode()), *args)

    def set_accessory(self, enabled):
        ok = self.send(self.application, 'setActivationPolicy:', ctypes.c_bool,
                       (ctypes.c_long,), (1 if enabled else 0,))
        if not ok:
            raise RuntimeError('macOS non ha accettato la modalità overlay.')

    def window(self, widget):
        return self.send(int(widget.winId()), 'window')

    def snapshot(self, widget):
        window = self.window(widget)
        if not window:
            raise RuntimeError('Finestra nativa macOS non disponibile.')
        return (window, self.send(window, 'level', ctypes.c_long),
                self.send(window, 'collectionBehavior', ctypes.c_ulong))

    def configure(self, widget, level):
        window = self.window(widget)
        is_panel = self.send(window, 'isKindOfClass:', ctypes.c_bool,
                             (ctypes.c_void_p,), (self.cls('NSPanel'),))
        if not is_panel:
            raise RuntimeError('La finestra overlay deve essere un pannello nativo macOS.')
        style = self.send(window, 'styleMask', ctypes.c_ulong)
        # Keep this flag for the lifetime of each panel; toggling it repeatedly
        # can desynchronize AppKit's activation state. Disable via policy/level.
        self.send(window, 'setStyleMask:', None, (ctypes.c_ulong,), (style | NONACTIVATING_PANEL,))
        self.send(window, 'setHidesOnDeactivate:', None, (ctypes.c_bool,), (False,))
        previous = self.send(window, 'collectionBehavior', ctypes.c_ulong)
        self.send(window, 'setCollectionBehavior:', None, (ctypes.c_ulong,), (overlay_behavior(previous),))
        self.send(window, 'setLevel:', None, (ctypes.c_long,), (level,))
        self.send(window, 'orderFrontRegardless', None)

    def focus(self, widget):
        self.send(self.window(widget), 'makeKeyAndOrderFront:', None,
                  (ctypes.c_void_p,), (None,))

    def restore(self, widget, snapshot):
        window, level, behavior = snapshot
        if self.window(widget) != window:
            return  # Qt has recreated this window; never message a stale pointer.
        self.send(window, 'setCollectionBehavior:', None, (ctypes.c_ulong,), (behavior,))
        self.send(window, 'setLevel:', None, (ctypes.c_long,), (level,))
        if widget.isVisible():
            self.send(window, 'orderFrontRegardless', None)


class MacOverlay(QObject):
    def __init__(self, app, pet, native=None):
        super().__init__(app)
        self.app, self.pet = app, pet
        self.native = native or AppKit()
        self.enabled = False
        self.error = ''
        self.snapshots = weakref.WeakKeyDictionary()
        self.app.installEventFilter(self)
        self.applying = False

    def prepare(self, widget):
        # Force NSPanel creation before the first show, including Qt file
        # dialogs and message boxes, so text input remains available fullscreen.
        if isinstance(widget, QMessageBox):
            widget.setOption(QMessageBox.Option.DontUseNativeDialog, True)
        elif isinstance(widget, QFileDialog):
            widget.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        if isinstance(widget, QDialog) and widget.windowType() != Qt.WindowType.Tool:
            # Window types are mutually exclusive values, not independent
            # flags: Sheet | Tool becomes SplashScreen, not an NSPanel.
            flags = widget.windowFlags() & ~Qt.WindowType.WindowType_Mask
            widget.setWindowFlags(flags | Qt.WindowType.Tool)
            widget.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)

    def apply(self, widget):
        if not self.enabled or self.applying or sip.isdeleted(widget) or not widget.isWindow():
            return
        self.applying = True
        try:
            current = self.native.snapshot(widget)
            saved = self.snapshots.get(widget)
            if saved is None or saved[0] != current[0]:
                self.snapshots[widget] = current
            level = self.window_level(widget)
            self.native.configure(widget, level)
        finally:
            self.applying = False

    def window_level(self, widget, seen=None):
        # Every nested window must be above its owner, including a message
        # opened by a modal reminder editor or a popup inside that message.
        seen = set() if seen is None else seen
        if widget in seen:
            return 1000
        seen.add(widget)
        parent = widget.parentWidget()
        owner = parent.window() if parent is not None else None
        parent_level = self.window_level(owner, seen) if owner is not None else 1000
        if widget is getattr(self.pet, 'bubble', None):
            return 1001
        if widget.windowType() == Qt.WindowType.ToolTip:
            return max(1004, parent_level + 1)
        if widget.windowType() == Qt.WindowType.Popup or isinstance(widget, QMenu):
            return max(1003, parent_level + 1)
        if isinstance(widget, QDialog):
            return max(1002 if widget.isModal() else 1001, parent_level + 1)
        return 1000

    def set_enabled(self, enabled):
        self.error = ''
        try:
            self.native.set_accessory(bool(enabled))
            self.enabled = bool(enabled)
            if self.enabled:
                for widget in self.app.topLevelWidgets():
                    if widget.isVisible():
                        self.prepare(widget)
                        self.apply(widget)
            else:
                self.restore_windows()
            return True
        except Exception as exc:
            self.fail(exc)
            return False

    def restore_windows(self):
        for widget, snapshot in list(self.snapshots.items()):
            if not sip.isdeleted(widget):
                self.native.restore(widget, snapshot)
        self.snapshots.clear()

    def fail(self, exc):
        self.enabled = False
        self.error = str(exc)
        logging.error('macOS overlay unavailable: %s', exc)
        try:
            self.restore_windows()
            self.native.set_accessory(False)
        except Exception:
            logging.exception('Could not fully restore macOS window state')
        if self.pet.panel:
            self.pet.panel.sync_mac_overlay()

    def eventFilter(self, obj, event):
        if not isinstance(obj, QWidget) or not obj.isWindow():
            return False
        try:
            if event.type() == QEvent.Type.Polish:
                self.prepare(obj)
            elif self.enabled and event.type() == QEvent.Type.Show:
                self.apply(obj)
                # Qt may update native flags as show() finishes.
                ref = weakref.ref(obj)
                QTimer.singleShot(0, lambda: self.apply_later(ref))
        except Exception as exc:
            self.fail(exc)
        return False

    def apply_later(self, ref):
        widget = ref()
        if widget is None or sip.isdeleted(widget) or not widget.isVisible():
            return
        try:
            self.apply(widget)
        except Exception as exc:
            self.fail(exc)
