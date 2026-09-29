"""Regressions for nested dialogs, file choosers and speech preferences."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from PyQt6.QtCore import Qt, QTimer, QDateTime
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QFileDialog, QComboBox, QLineEdit
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_dialogs import exec_dialog, choose_files
from yun_jin_macos import MacOverlay
from yun_jin_panel import ReminderDialog
from yun_jin_speech import Speech
import yun_jin_dialogs as dialogs

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class DialogSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.pet = Companion(self.store)
        for timer in (self.pet.timer, self.pet.reminder_timer, self.pet.checkpoint_timer,
                      self.pet.updates.initial, self.pet.updates.timer):
            timer.stop()
        self.levels = {}
        self.native = Mock()
        self.native.snapshot.side_effect = lambda w: (int(w.winId()), self.levels.get(w, 0), 0)
        self.native.configure.side_effect = lambda w, level: self.levels.__setitem__(w, level)
        self.controller = MacOverlay(app, self.pet, self.native)
        self.pet.mac_overlay = self.controller
        self.controller.set_enabled(True)
        self.pet.open_panel(tab=2)
        self.panel = self.pet.panel
        app.processEvents()

    def tearDown(self):
        self.controller.set_enabled(False)
        app.removeEventFilter(self.controller)
        self.pet.mac_overlay = None
        self.controller.deleteLater()
        self.pet.close(); self.pet.deleteLater()
        app.processEvents()
        self.store.close(); self.tmp.cleanup()

    def during_dialog(self, action, inspect):
        errors = []; seen = []
        timer = QTimer(); timer.setSingleShot(True)
        def check():
            dialog = app.activeModalWidget()
            seen.append(dialog)
            try:
                self.assertIsNotNone(dialog)
                inspect(dialog)
            except Exception as exc:
                errors.append(exc)
            finally:
                if dialog is not None and dialog.isVisible():
                    dialog.reject()
        timer.timeout.connect(check); timer.start(40)
        try:
            result = action()
        finally:
            timer.stop()
        self.assertTrue(seen, 'Dialog did not enter an event loop')
        if errors:
            raise errors[0]
        return result

    def assert_above_owner(self, dialog, owner):
        self.assertIs(dialog.parentWidget(), owner)
        self.assertEqual(dialog.windowModality(), Qt.WindowModality.WindowModal)
        self.assertEqual(dialog.windowType(), Qt.WindowType.Tool)
        if self.controller.enabled:
            self.assertGreater(self.levels[dialog], self.levels[owner])
            self.native.focus.assert_any_call(dialog)

    def test_shortcuts_and_material_errors_overlay_on_and_off(self):
        for enabled in (True, False):
            self.controller.set_enabled(enabled)
            with patch.object(dialogs, 'sys', SimpleNamespace(platform='darwin')):
                def inspect(box):
                    self.assert_above_owner(box, self.panel)
                    self.assertTrue(box.testOption(QMessageBox.Option.DontUseNativeDialog))
                    box.button(QMessageBox.StandardButton.Ok).click()
                self.during_dialog(self.panel.show_shortcuts, inspect)
                self.panel.note_path = str(Path(self.tmp.name) / 'missing.txt')
                self.during_dialog(self.panel.open_material, inspect)
            self.assertIsNone(app.activeModalWidget())
            self.assertTrue(self.panel.isEnabled())

    def test_nested_date_warning_and_popup_above_reminder_editor(self):
        editor = ReminderDialog(self.pet)
        editor.title.setText('Prova'); editor.kind.setCurrentIndex(1)
        editor.when.setDateTime(QDateTime.currentDateTime().addSecs(-60))
        def inspect_editor(dialog):
            self.assert_above_owner(dialog, self.panel)
            def inspect_warning(box):
                self.assert_above_owner(box, editor)
                self.assertEqual(box.windowTitle(), 'Data passata')
                combo = QComboBox(box); combo.addItems(['Uno', 'Due']); combo.show()
                combo.showPopup(); app.processEvents()
                self.assertGreater(self.levels[combo.view().window()], self.levels[box])
                combo.hidePopup()
                box.button(QMessageBox.StandardButton.Ok).click()
            self.during_dialog(editor.submit, inspect_warning)
            self.assertTrue(editor.isVisible())
        self.during_dialog(lambda: exec_dialog(editor, self.pet), inspect_editor)
        editor.deleteLater()
        self.assertEqual(self.store.reminders(True), [])

    def test_delete_confirmations_cancel_and_confirm(self):
        rid = self.store.add_reminder('Da conservare', time.time() + 600)
        self.panel.refresh_reminders(force=True)
        self.panel.reminders.setCurrentItem(self.panel.reminders.topLevelItem(0))
        def answer(box, button):
            self.assert_above_owner(box, self.panel)
            self.assertEqual(box.standardButton(box.defaultButton()), QMessageBox.StandardButton.No)
            box.button(button).click()
        self.during_dialog(self.panel.delete_reminder, lambda b: answer(b, QMessageBox.StandardButton.No))
        self.assertEqual(len(self.store.reminders(True)), 1)
        self.during_dialog(self.panel.delete_reminder, lambda b: answer(b, QMessageBox.StandardButton.Yes))
        self.assertEqual(self.store.reminders(True), [])
        self.panel.new_note(); self.panel.title.setText('Conserva appunto')
        self.panel.dirty = True; self.panel.save_note(); note_id = self.panel.note_id
        self.during_dialog(self.panel.delete_note, lambda b: answer(b, QMessageBox.StandardButton.No))
        self.assertEqual(self.panel.note_id, note_id)

    def test_file_choosers_cancel_without_import_or_backup(self):
        with patch.object(dialogs, 'sys', SimpleNamespace(platform='darwin')), \
             patch.object(self.pet, 'add_paths') as add, patch.object(self.store, 'export_backup') as export:
            for enabled in (True, False):
                self.controller.set_enabled(enabled)
                for action, mode in ((self.panel.add_file, QFileDialog.FileMode.ExistingFiles),
                                     (self.panel.add_folder, QFileDialog.FileMode.Directory),
                                     (self.panel.backup, QFileDialog.FileMode.AnyFile),
                                     (self.panel.music.export_laps, QFileDialog.FileMode.AnyFile)):
                    def inspect(dialog):
                        self.assertIsInstance(dialog, QFileDialog)
                        self.assert_above_owner(dialog, self.panel)
                        self.assertTrue(dialog.testOption(QFileDialog.Option.DontUseNativeDialog))
                        self.assertEqual(dialog.fileMode(), mode)
                    self.during_dialog(action, inspect)
            add.assert_not_called(); export.assert_not_called()

    def test_csv_export_accepts_selection_and_uses_csv_suffix(self):
        self.panel.music.watch.laps = [{'split': 1.25, 'total': 1.25}]
        target = Path(self.tmp.name) / 'laps'
        def accept(dialog):
            self.assert_above_owner(dialog, self.panel)
            self.assertEqual(dialog.defaultSuffix(), 'csv')
            # Type into the visible chooser: selectFile() keeps its old text
            # once the filename editor has focus.
            dialog.findChild(QLineEdit, 'fileNameEdit').setText(str(target)); dialog.accept()
        self.during_dialog(self.panel.music.export_laps, accept)
        content = target.with_suffix('.csv').read_text(encoding='utf-8-sig')
        self.assertIn('1,1.25,1.25', content)

    def test_existing_backup_requires_confirmation_and_no_keeps_original(self):
        target = Path(self.tmp.name) / 'existing.zip'; target.write_bytes(b'original')
        stages = []; errors = []; timer = QTimer()
        def advance():
            dialog = app.activeModalWidget()
            try:
                if isinstance(dialog, QFileDialog):
                    if not stages:
                        stages.append('selected'); dialog.selectFile(str(target)); dialog.accept()
                    elif stages[-1] == 'declined':
                        stages.append('cancelled'); dialog.reject()
                elif isinstance(dialog, QMessageBox):
                    self.assert_above_owner(dialog, self.panel)
                    self.assertEqual(dialog.windowTitle(), 'Sostituisci file')
                    stages.append('declined'); dialog.button(QMessageBox.StandardButton.No).click()
            except Exception as exc:
                errors.append(exc)
                if dialog is not None:dialog.reject()
        timer.timeout.connect(advance); timer.start(30)
        try:
            result = choose_files(self.panel, 'Backup', mode='save', filename=str(target))
        finally:
            timer.stop()
        if errors:raise errors[0]
        self.assertEqual(stages, ['selected', 'declined', 'cancelled'])
        self.assertEqual(result, []); self.assertEqual(target.read_bytes(), b'original')

    def test_legacy_voice_preferences_migrate_once_and_manual_reading_still_works(self):
        self.pet.speech.shutdown()
        for enabled, reminders in ((False, False), (False, True), (True, False), (True, True)):
            self.store.set_preference('tts_enabled', enabled)
            self.store.set_preference('tts_reminders', reminders)
            self.store.set_preference('tts_auto_reminders', None)
            voice = Speech(self.pet); self.pet.speech = voice
            self.assertEqual(voice.pref('auto_reminders', None), enabled and reminders)
            voice.player = Mock(); voice.output = Mock()
            with patch('yun_jin_speech.QProcess'):
                voice.set_pref('auto_reminders', False)
                self.assertFalse(voice.speak('Promemoria', category='reminder'))
                self.assertTrue(voice.speak('Testo richiesto', category='manual'))
                voice.set_pref('auto_reminders', False)
                self.assertTrue(voice.busy, 'Automatic opt-out must not stop manual speech')
                voice.stop(announce=False)
                voice.set_pref('auto_reminders', True)
                self.assertTrue(voice.speak('Promemoria', category='reminder'))
                voice.set_pref('auto_reminders', False)
                self.assertFalse(voice.busy)
            voice.shutdown()
        # A new choice must survive reopening even with legacy switches enabled.
        again = Speech(self.pet); self.pet.speech = again
        self.assertFalse(again.pref('auto_reminders', True))

    def test_sound_options_preserve_choices_while_disabled(self):
        p = self.panel
        p.interaction_sounds.setChecked(True)
        old_volume = p.volume.value()
        p.sound_enabled.setChecked(False)
        self.assertFalse(p.interaction_sounds.isEnabled()); self.assertFalse(p.volume.isEnabled())
        self.assertFalse(self.pet.sound.enabled)
        p.sound_enabled.setChecked(True)
        self.assertTrue(p.interaction_sounds.isEnabled()); self.assertTrue(p.interaction_sounds.isChecked())
        self.assertEqual(p.volume.value(), old_volume)
        self.assertGreater(p.interaction_sounds.mapTo(p, p.interaction_sounds.rect().topLeft()).y(),
                           p.sound_enabled.mapTo(p, p.sound_enabled.rect().bottomLeft()).y())


if __name__ == '__main__':
    unittest.main(verbosity=2)
