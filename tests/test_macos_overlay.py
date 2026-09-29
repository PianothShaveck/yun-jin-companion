import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget, QDialog, QMenu, QComboBox, QMessageBox
from yun_jin_macos import (MacOverlay, AppKit, PREFERENCE, overlay_behavior,
    MOVE_TO_ACTIVE_SPACE, FULLSCREEN_PRIMARY, FULLSCREEN_NONE, PRIMARY, AUXILIARY,
    JOIN_SPACES, FULLSCREEN_AUXILIARY, JOIN_APPLICATIONS)
from yun_jin_data import Store

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class FakeNative:
    def __init__(self):
        self.accessory = False
        self.states = {}
        self.fail_widget = None

    def set_accessory(self, enabled):
        self.accessory = enabled

    def snapshot(self, widget):
        return self.states.setdefault(widget, (int(widget.winId()), 3, 16))

    def configure(self, widget, level):
        if widget is self.fail_widget:
            raise RuntimeError('native failure')
        handle, _, behavior = self.snapshot(widget)
        self.states[widget] = (handle, level, overlay_behavior(behavior))

    def restore(self, widget, state):
        self.states[widget] = state


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.pet = QWidget(None, Qt.WindowType.Tool)
        self.pet.panel = None
        self.pet.show()
        self.native = FakeNative()
        self.controller = MacOverlay(app, self.pet, self.native)
        self.windows = [self.pet]

    def tearDown(self):
        self.controller.set_enabled(False)
        app.removeEventFilter(self.controller)
        for widget in self.windows:
            widget.close()
            widget.deleteLater()
        self.controller.deleteLater()
        app.processEvents()

    def test_default_and_saved_opt_out_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            self.assertTrue(store.preference(PREFERENCE, True))
            store.set_preference(PREFERENCE, False)
            store.close()
            store = Store(tmp)
            self.assertFalse(store.preference(PREFERENCE, True))
            store.close()

    def test_conflicting_flags_removed_other_flags_preserved(self):
        conflict = MOVE_TO_ACTIVE_SPACE | FULLSCREEN_PRIMARY | FULLSCREEN_NONE | PRIMARY | AUXILIARY
        actual = overlay_behavior(conflict | 16)
        self.assertEqual(actual & conflict, 0)
        self.assertEqual(actual, JOIN_SPACES | FULLSCREEN_AUXILIARY | JOIN_APPLICATIONS | 16)

    def test_enable_disable_restores_original_native_state(self):
        before = self.native.snapshot(self.pet)
        for _ in range(2):
            self.assertTrue(self.controller.set_enabled(True))
            self.assertTrue(self.native.accessory)
            self.assertEqual(self.native.snapshot(self.pet)[1], 1000)
            self.assertTrue(self.controller.set_enabled(False))
            self.assertFalse(self.native.accessory)
            self.assertEqual(self.native.snapshot(self.pet), before)

    def test_dialogs_and_popups_stay_above_character(self):
        self.controller.set_enabled(True)
        for widget, modal, expected in [(QDialog(), False, 1001), (QDialog(), True, 1002), (QMenu(), False, 1003)]:
            self.windows.append(widget)
            if isinstance(widget, QDialog):
                widget.setModal(modal)
                self.controller.prepare(widget)
                self.assertEqual(widget.windowType(), Qt.WindowType.Tool)
            self.controller.apply(widget)
            self.assertEqual(self.native.snapshot(widget)[1], expected)

    def test_failure_restores_dock_and_existing_window_levels(self):
        before = self.native.snapshot(self.pet)
        self.controller.set_enabled(True)
        self.native.fail_widget = self.pet
        self.assertFalse(self.controller.set_enabled(True))
        self.assertFalse(self.native.accessory)
        self.assertFalse(self.controller.enabled)
        self.assertIn('native failure', self.controller.error)
        self.assertEqual(self.native.snapshot(self.pet), before)

    def test_window_modal_message_becomes_tool_not_splash_screen(self):
        self.controller.set_enabled(True)
        panel = QDialog(self.pet); self.windows.append(panel)
        self.controller.prepare(panel); self.controller.apply(panel)
        box = QMessageBox(panel); self.windows.append(box)
        box.setWindowModality(Qt.WindowModality.WindowModal)
        hints = box.windowFlags() & ~Qt.WindowType.WindowType_Mask
        self.controller.prepare(box)
        self.assertEqual(box.windowType(), Qt.WindowType.Tool)
        self.assertEqual(box.windowFlags() & ~Qt.WindowType.WindowType_Mask, hints)
        self.assertEqual(box.windowModality(), Qt.WindowModality.WindowModal)
        self.controller.apply(box)
        self.assertGreater(self.native.snapshot(box)[1], self.native.snapshot(panel)[1])

    def test_combobox_popup_above_settings_and_modal_dialog(self):
        self.controller.set_enabled(True)
        dialog=QDialog(self.pet);self.windows.append(dialog)
        dialog.setModal(True);combo=QComboBox(dialog);combo.addItems(['Microsoft Edge','Google Translate'])
        dialog.show();app.processEvents();combo.showPopup();app.processEvents()
        popup=combo.view().window()
        self.assertEqual(popup.windowType(),Qt.WindowType.Popup)
        self.assertTrue(popup.isVisible())
        self.assertGreater(self.native.snapshot(popup)[1],self.native.snapshot(dialog)[1])
        combo.hidePopup()

    def test_native_bridge_refuses_non_panel(self):
        bridge = object.__new__(AppKit)
        bridge.window = lambda widget: 123
        bridge.cls = lambda name: 456
        bridge.send = lambda *args, **kwargs: False
        with self.assertRaisesRegex(RuntimeError, 'pannello'):
            bridge.configure(self.pet, 1000)

    def test_native_bridge_configures_panel_without_activating_app(self):
        calls = []
        bridge = object.__new__(AppKit)
        bridge.window = lambda widget: 123
        bridge.cls = lambda name: 456
        def send(receiver, selector, result=None, types=(), args=()):
            calls.append((selector, args))
            return {'isKindOfClass:': True, 'styleMask': 0,
                    'collectionBehavior': FULLSCREEN_PRIMARY | PRIMARY}.get(selector)
        bridge.send = send
        bridge.configure(self.pet, 1000)
        self.assertIn(('setLevel:', (1000,)), calls)
        self.assertIn(('setCollectionBehavior:', (overlay_behavior(0),)), calls)
        self.assertIn(('setStyleMask:', (128,)), calls)
        self.assertIn(('orderFrontRegardless', ()), calls)
        self.assertFalse(any('activate' in selector.lower() and selector != 'setHidesOnDeactivate:'
                             for selector, args in calls))

    def test_user_toggle_persists_only_after_success(self):
        from types import SimpleNamespace
        from yun_jin_app import Companion
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            pet = SimpleNamespace(mac_overlay=self.controller, store=store, panel=None)
            with patch('yun_jin_app.mac_dock_icon'):
                self.assertTrue(Companion.set_mac_overlay(pet, False))
                self.assertFalse(store.preference(PREFERENCE, True))
                self.native.fail_widget = self.pet
                self.assertFalse(Companion.set_mac_overlay(pet, True))
                self.assertFalse(store.preference(PREFERENCE, True))
            store.close()

    @unittest.skipUnless(sys.platform == 'darwin' and app.platformName() == 'cocoa',
                         'Requires a real macOS desktop with QT_QPA_PLATFORM=cocoa')
    def test_native_panel_policy_and_roundtrip(self):
        app.removeEventFilter(self.controller)
        native = AppKit()
        self.controller = MacOverlay(app, self.pet, native)
        before = native.snapshot(self.pet)
        self.assertTrue(self.controller.set_enabled(True), self.controller.error)
        self.assertEqual(native.snapshot(self.pet)[1], 1000)
        self.assertTrue(self.controller.set_enabled(False), self.controller.error)
        self.assertEqual(native.snapshot(self.pet), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
