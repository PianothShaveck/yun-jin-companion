"""Windows layering, focus preservation and bounded background work."""
import ctypes as C
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QApplication, QWidget
import yun_jin_windows_overlay as overlay


class FakeWindows:
    PET, FRONT = 0x100000007, 0x100000009

    def __init__(self):
        self.order = [self.FRONT, self.PET]
        self.foreground = self.FRONT
        self.pid = os.getpid() + 100
        self.style = overlay.WS_EX_TOPMOST
        self.front_style = 0
        self.monitor_rect = (0, 0, 1920, 1080)
        self.hidden, self.minimized = set(), set()
        self.rects = {self.PET: (1700, 800, 1830, 980), self.FRONT: (0, 0, 1920, 1080)}
        self.api = types.SimpleNamespace(
            GetForegroundWindow=Mock(side_effect=lambda: self.foreground),
            GetShellWindow=Mock(return_value=999),
            GetDesktopWindow=Mock(return_value=998),
            GetWindow=Mock(side_effect=self.previous),
            GetWindowThreadProcessId=Mock(side_effect=self.process),
            GetWindowLongPtrW=Mock(side_effect=lambda h,kind: self.style if kind==overlay.GWL_EXSTYLE else self.front_style),
            GetWindowLongW=Mock(side_effect=lambda h,kind: self.style if kind==overlay.GWL_EXSTYLE else self.front_style),
            GetWindowRect=Mock(side_effect=self.rectangle),
            MonitorFromWindow=Mock(return_value=0x100000077),
            GetMonitorInfoW=Mock(side_effect=self.monitor),
            IsWindowVisible=Mock(side_effect=lambda h: h not in self.hidden),
            IsIconic=Mock(side_effect=lambda h: h in self.minimized),
            SetWindowPos=Mock(side_effect=self.position),
            SetWinEventHook=Mock(return_value=123),
            UnhookWinEvent=Mock(return_value=1),
        )

    def monitor(self, handle, output):
        info=C.cast(output,C.POINTER(overlay.MonitorInfo)).contents
        assert info.cbSize==C.sizeof(overlay.MonitorInfo)
        info.rcMonitor.left,info.rcMonitor.top,info.rcMonitor.right,info.rcMonitor.bottom=self.monitor_rect
        return 1

    def previous(self, hwnd, command):
        assert command == overlay.GW_HWNDPREV
        index = self.order.index(hwnd)
        return self.order[index - 1] if index else 0

    def process(self, hwnd, output):
        C.cast(output, C.POINTER(W.DWORD))[0] = self.pid
        return 77

    def rectangle(self, hwnd, output):
        rect = C.cast(output, C.POINTER(W.RECT)).contents
        rect.left, rect.top, rect.right, rect.bottom = self.rects[hwnd]
        return 1

    def position(self, hwnd, after, x, y, width, height, flags):
        assert after == overlay.HWND_TOPMOST
        assert flags == overlay.POSITION_FLAGS
        self.order.remove(hwnd)
        self.order.insert(0, hwnd)
        self.style |= overlay.WS_EX_TOPMOST
        return 1


class NativeLogicTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeWindows()
        self.native = overlay.NativeTopmost(self.fake.api)

    def test_fullscreen_detection_uses_the_pet_monitor_and_ignores_desktop_and_normal_windows(self):
        f=self.fake
        self.assertTrue(self.native.fullscreen(f.PET))
        f.front_style=overlay.WS_CAPTION
        self.assertFalse(self.native.fullscreen(f.PET))
        f.front_style=0
        f.monitor_rect=(-1920,0,0,1080)
        self.assertFalse(self.native.fullscreen(f.PET))
        f.monitor_rect=(0,0,1920,1080)
        f.rects[f.FRONT]=(0,0,1920,1040)
        self.assertFalse(self.native.fullscreen(f.PET))
        f.rects[f.FRONT]=(0,0,1920,1080)
        for hwnd in (0,f.PET,998,999):
            f.foreground=hwnd
            self.assertFalse(self.native.fullscreen(f.PET))
        f.foreground=f.FRONT;f.minimized.add(f.FRONT)
        self.assertFalse(self.native.fullscreen(f.PET))
        f.minimized.clear();f.pid=os.getpid()
        self.assertFalse(self.native.fullscreen(f.PET))

    def test_another_topmost_fullscreen_window_is_recovered_without_focus_or_geometry_changes(self):
        before = dict(self.fake.rects)
        self.assertTrue(self.native.restore(self.fake.PET))
        self.assertEqual(self.fake.order, [self.fake.PET, self.fake.FRONT])
        self.assertEqual(self.fake.foreground, self.fake.FRONT)
        self.assertEqual(self.fake.rects, before)
        flags = self.fake.api.SetWindowPos.call_args.args[-1]
        self.assertTrue(flags & 0x10)  # SWP_NOACTIVATE
        self.assertFalse(flags & (0x40 | 0x80))  # Neither show nor hide.
        self.assertIs(self.fake.api.GetWindow.restype, W.HWND)

    def test_lost_topmost_flag_is_repaired_and_repeated_checks_do_not_raise_again(self):
        self.fake.style = 0
        self.assertTrue(self.native.restore(self.fake.PET))
        for _ in range(100):
            self.assertFalse(self.native.restore(self.fake.PET))
        self.fake.api.SetWindowPos.assert_called_once()

    def test_entering_fullscreen_on_the_same_foreground_window_is_detected(self):
        self.fake.order = [self.fake.PET, self.fake.FRONT]
        self.assertFalse(self.native.restore(self.fake.PET))
        self.fake.order = [self.fake.FRONT, self.fake.PET]
        self.assertTrue(self.native.restore(self.fake.PET))

    def test_hidden_minimized_and_own_dialog_windows_are_left_alone(self):
        for hwnd in (self.fake.PET, self.fake.FRONT):
            for state in (self.fake.hidden, self.fake.minimized):
                with self.subTest(hwnd=hwnd, state=id(state)):
                    state.add(hwnd)
                    self.assertFalse(self.native.restore(self.fake.PET))
                    state.clear()
        self.fake.pid = os.getpid()
        self.assertFalse(self.native.restore(self.fake.PET))
        self.fake.foreground = self.fake.PET
        self.assertFalse(self.native.restore(self.fake.PET))
        self.fake.foreground = 0
        self.assertFalse(self.native.restore(self.fake.PET))
        self.fake.api.SetWindowPos.assert_not_called()

    def test_other_monitor_and_disappearing_windows_do_not_restack_the_pet(self):
        self.fake.rects[self.fake.FRONT] = (-1920, 0, 0, 1080)
        self.assertFalse(self.native.restore(self.fake.PET))
        self.fake.api.GetWindowRect.side_effect = None
        self.fake.api.GetWindowRect.return_value = 0
        self.assertFalse(self.native.restore(self.fake.PET))
        self.fake.api.GetWindowThreadProcessId.side_effect = None
        self.fake.api.GetWindowThreadProcessId.return_value = 0
        self.assertFalse(self.native.restore(self.fake.PET))
        self.fake.api.SetWindowPos.assert_not_called()

    def test_changing_window_order_has_a_finite_traversal(self):
        self.fake.api.GetWindow.side_effect = lambda hwnd, _: 41 if hwnd != 41 else 42
        self.assertFalse(self.native.restore(self.fake.PET))
        self.assertLessEqual(self.fake.api.GetWindow.call_count, 4)
        self.fake.api.GetWindow.side_effect = lambda hwnd, _: hwnd + 10
        self.fake.api.GetWindow.reset_mock()
        self.assertFalse(self.native.restore(self.fake.PET))
        self.assertLessEqual(self.fake.api.GetWindow.call_count, 513)

    def test_failed_position_is_reported(self):
        self.fake.api.SetWindowPos.side_effect = None
        self.fake.api.SetWindowPos.return_value = 0
        with self.assertRaises(OSError):
            self.native.restore(self.fake.PET)

    def test_foreground_hook_uses_gui_notifications_and_closes_once(self):
        changed = Mock()
        with patch.object(C, 'WINFUNCTYPE', C.CFUNCTYPE, create=True):
            self.native.watch(changed)
        args = self.fake.api.SetWinEventHook.call_args.args
        self.assertEqual(args[:3], (0x0003, 0x0003, None))
        self.assertEqual(args[4:], (0, 0, 0x0002))
        self.native.callback(123, 3, self.fake.FRONT, 0, 0, 0, 0)
        changed.assert_called_once()
        self.native.close()
        self.native.close()
        self.fake.api.UnhookWinEvent.assert_called_once_with(123)
        self.native.callback(123, 3, self.fake.FRONT, 0, 0, 0, 0)
        changed.assert_called_once()


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.pet = QWidget()
        self.pet.closing = False
        self.pet.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.native = Mock()
        self.controller = overlay.WindowsOverlay(self.app, self.pet, self.native)

    def tearDown(self):
        self.controller.close()
        self.pet.close()
        self.pet.deleteLater()
        self.controller.deleteLater()
        self.app.processEvents()

    def show_pet(self):
        self.pet.show()
        self.app.processEvents()
        self.controller.pending.stop()
        self.native.restore.reset_mock()

    def test_show_and_coalesced_notifications_do_not_depend_on_animation_or_focus_mode(self):
        self.assertFalse(self.controller.timer.isActive())
        self.show_pet()
        self.assertTrue(self.controller.timer.isActive())
        self.assertEqual(self.controller.timer.interval(), 1000)
        self.pet.paused = True
        self.pet.mode = 'asleep'
        self.pet.focus_active = lambda: True
        with patch.object(self.controller.pending, 'start', wraps=self.controller.pending.start) as start:
            for _ in range(100):
                self.native.watch.call_args.args[0]()
            start.assert_called_once()
        self.controller.refresh()
        self.native.restore.assert_called_once_with(int(self.pet.effectiveWinId()))

    def test_hidden_and_minimized_pet_is_not_reopened(self):
        self.show_pet()
        self.pet.hide()
        self.controller.refresh()
        self.assertFalse(self.controller.timer.isActive())
        self.assertFalse(self.controller.pending.isActive())
        self.native.restore.assert_not_called()
        self.show_pet()
        self.pet.showMinimized()
        self.app.processEvents()
        self.controller.refresh()
        self.assertFalse(self.controller.timer.isActive())
        self.native.restore.assert_not_called()
        self.pet.showNormal()
        self.app.processEvents()
        self.assertTrue(self.controller.timer.isActive())

    def test_recreated_native_handle_is_used_and_no_handle_is_forced_for_hidden_pet(self):
        self.show_pet()
        with patch.object(self.pet, 'effectiveWinId', return_value=0x100000099):
            self.controller.refresh()
        self.native.restore.assert_called_once_with(0x100000099)
        self.pet.hide()
        with patch.object(self.pet, 'winId') as win_id:
            self.controller.refresh()
        win_id.assert_not_called()

    def test_fullscreen_opt_out_recovers_automatically_and_respects_manual_hide(self):
        self.pet.character_hidden=False;self.pet.fullscreen_hidden=False
        def suppress(value):
            self.pet.fullscreen_hidden=value
            self.pet.setVisible(not value and not self.pet.character_hidden)
        self.pet.set_fullscreen_hidden=suppress
        self.show_pet()
        self.assertTrue(self.controller.enabled)
        self.native.fullscreen.return_value=True
        self.controller.set_enabled(False)
        self.assertFalse(self.pet.isVisible());self.assertTrue(self.pet.fullscreen_hidden)
        self.assertTrue(self.controller.timer.isActive())
        self.native.restore.assert_not_called()
        self.native.fullscreen.return_value=False
        self.controller.refresh()
        self.assertTrue(self.pet.isVisible());self.assertFalse(self.pet.fullscreen_hidden)
        self.native.fullscreen.return_value=True
        self.controller.refresh()
        self.pet.character_hidden=True;self.pet.hide();self.controller.sync_visibility()
        self.controller.set_enabled(True)
        self.assertFalse(self.pet.isVisible());self.assertFalse(self.controller.timer.isActive())
        self.pet.character_hidden=False;self.pet.show();self.controller.refresh()
        self.assertTrue(self.pet.isVisible())

    def test_cancelled_close_does_not_disable_overlay_and_shutdown_cancels_pending_work(self):
        self.show_pet()
        self.controller.eventFilter(self.pet, QEvent(QEvent.Type.Close))
        self.assertTrue(self.controller.timer.isActive())
        self.controller.request()
        self.controller.close()
        self.controller.close()
        self.controller.refresh()
        self.native.close.assert_called_once()
        self.native.restore.assert_not_called()
        self.assertFalse(self.controller.timer.isActive())
        self.assertFalse(self.controller.pending.isActive())

    def test_native_errors_are_bounded_and_recovery_is_retried(self):
        self.show_pet()
        self.native.restore.side_effect = OSError('temporarily unavailable')
        with patch.object(overlay.logging, 'exception') as log:
            for _ in range(10):
                self.controller.refresh()
            log.assert_called_once()
        self.native.restore.side_effect = None
        self.controller.refresh()
        self.assertFalse(self.controller.failed)

    def test_factory_is_inert_on_other_platforms_and_offscreen(self):
        with patch.object(overlay, 'WindowsOverlay') as create:
            for platform in ('darwin', 'linux', 'win32'):
                with patch.object(overlay.sys, 'platform', platform):
                    self.assertIsNone(overlay.install_windows_overlay(Mock(platformName=lambda: 'offscreen'), self.pet))
            create.assert_not_called()


class NativeWindowsTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Requires native Windows window manager')
    def test_fullscreen_z_order_and_foreground_are_preserved(self):
        env = dict(os.environ, QT_QPA_PLATFORM='windows')
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--native'],
                       env=env, check=True, timeout=30)


def native_probe():
    """Exercise real HWNDs against a fullscreen window in a second process."""
    import time
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    user = C.WinDLL('user32', use_last_error=True)
    native = overlay.NativeTopmost(user)
    pet = QWidget()
    pet.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    pet.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    pet.resize(120, 160)
    pet.move(app.primaryScreen().geometry().center())
    pet.show()
    app.processEvents()
    hwnd = int(pet.winId())
    caption = QWidget(pet, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
    caption.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    caption.resize(150, 60)
    caption.move(pet.pos())
    caption.show()
    app.processEvents()
    caption_hwnd = int(caption.winId())
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / 'window.txt'
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--foreign', str(state)])
        controller = None
        try:
            deadline = time.monotonic() + 10
            while not state.exists() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.02)
            assert state.exists(), 'Foreign fullscreen window did not start'
            other = int(state.read_text())
            # Actual Windows foreground policy varies on CI. Override only its
            # identity query; layering, HWNDs, rectangles and focus stay native.
            class ForegroundProxy:
                GetForegroundWindow = Mock(return_value=other)
                def __getattr__(self, name):
                    return getattr(user, name)
            native = overlay.NativeTopmost(ForegroundProxy())
            controller = overlay.WindowsOverlay(app, pet, native)
            pet.character_hidden=False;pet.fullscreen_hidden=False
            def suppress(value):
                pet.fullscreen_hidden=value
                pet.setVisible(not value and not pet.character_hidden)
            pet.set_fullscreen_hidden=suppress
            assert native.hook, 'Foreground hook was not registered'
            controller.pending.stop()
            def above(a, b):
                handle = user.GetWindow(b, overlay.GW_HWNDPREV)
                for _ in range(512):
                    if not handle: return False
                    if handle == a: return True
                    handle = user.GetWindow(handle, overlay.GW_HWNDPREV)
                return False
            for _ in range(3):
                assert user.SetWindowPos(hwnd, -2, 0, 0, 0, 0, overlay.POSITION_FLAGS)
                assert user.SetWindowPos(hwnd, -1, 0, 0, 0, 0, overlay.POSITION_FLAGS)
                assert user.SetWindowPos(other, -1, 0, 0, 0, 0, overlay.POSITION_FLAGS)
                assert above(other, hwnd), 'Fullscreen window must cover the pet before recovery'
                foreground = user.GetForegroundWindow()
                geometry = pet.geometry()
                controller.refresh()
                assert above(hwnd, other), 'Pet was not restored above fullscreen window'
                assert above(caption_hwnd, hwnd), 'Caption must stay above its owner'
                assert user.GetForegroundWindow() == foreground, 'Overlay stole foreground focus'
                assert pet.geometry() == geometry
            # Same HWND enters fullscreen without a foreground notification:
            # the periodic check must recover it without animation ticks.
            native.close()
            controller.pending.stop()
            assert controller.timer.isActive()
            user.SetWindowPos(other, -1, 0, 0, 0, 0, overlay.POSITION_FLAGS)
            deadline = time.monotonic() + 3
            while not above(hwnd, other) and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.02)
            assert above(hwnd, other), 'Fallback check did not restore overlay'
            assert native.fullscreen(hwnd), 'Real fullscreen window was not detected'
            foreground=user.GetForegroundWindow()
            controller.set_enabled(False)
            assert not pet.isVisible() and controller.timer.isActive(), 'Opt-out must hide and keep watching'
            assert user.GetForegroundWindow()==foreground, 'Hiding pet stole focus'
            native.user.GetForegroundWindow.return_value=user.GetDesktopWindow()
            controller.refresh()
            assert pet.isVisible(), 'Pet did not return on desktop'
            native.user.GetForegroundWindow.return_value=other
            controller.refresh()
            assert not pet.isVisible(), 'Pet must hide on returning to fullscreen'
            controller.set_enabled(True)
            assert pet.isVisible() and above(hwnd,other), 'Enabling overlay did not restore pet'
            controller.close()
        finally:
            if controller is not None:
                controller.close()
            child.terminate()
            child.wait(timeout=5)
            caption.close()
            pet.close()
    print('PASS native fullscreen layering and no focus theft')


def foreign_window(path):
    app = QApplication([])
    window = QWidget()
    window.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    window.showFullScreen()
    app.processEvents()
    target = Path(path)
    staged = target.with_suffix('.tmp')
    staged.write_text(str(int(window.winId())))
    staged.replace(target)
    sys.exit(app.exec())


if __name__ == '__main__':
    if sys.argv[1:2] == ['--native']:
        native_probe()
    elif sys.argv[1:2] == ['--foreign']:
        foreign_window(sys.argv[2])
    else:
        unittest.main(verbosity=2)
