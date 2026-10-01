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
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, QDateTime, QUrl
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QFileDialog, QComboBox, QLineEdit, QPushButton, QLabel
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

    def dialog_ready(self, dialog):
        if dialog is None or sip.isdeleted(dialog) or not dialog.isVisible():
            return False
        if not self.controller.enabled:
            return True
        # Construction/font discovery/file models may take longer than a fixed
        # timer on CI. Inspect only after the application's deferred focus ran.
        return (dialog in self.levels and
                any(call.args and call.args[0] is dialog
                    for call in self.native.focus.call_args_list))

    def drive_dialogs(self, action, step, timeout=5):
        errors = []; timer = QTimer(); deadline = time.monotonic() + timeout
        def advance():
            # An inspection can itself open a nested modal dialog. Its own
            # driver must run without re-entering this driver's current step.
            timer.stop()
            dialog = app.activeModalWidget()
            try:
                if time.monotonic() >= deadline and not errors:
                    title = dialog.windowTitle() if dialog is not None else '(none)'
                    errors.append(AssertionError('Dialog timeout: ' + title))
                if errors:
                    if dialog is not None and not sip.isdeleted(dialog):
                        dialog.reject()
                elif self.dialog_ready(dialog):
                    step(dialog)
            except Exception as exc:
                errors.append(exc)
                if dialog is not None and not sip.isdeleted(dialog):
                    dialog.reject()
            finally:
                # Keep draining after a failure: a cancelled overwrite question
                # reopens the file chooser, which must also be cancelled.
                timer.start(10)
        timer.timeout.connect(advance); timer.start(0)
        try:
            result = action()
        finally:
            timer.stop()
        if errors:
            raise errors[0]
        return result

    def during_dialog(self, action, inspect):
        seen = []
        def step(dialog):
            self.assertFalse(seen, 'Unexpected extra dialog: ' + dialog.windowTitle())
            seen.append(dialog)
            try:
                inspect(dialog)
            finally:
                if not sip.isdeleted(dialog) and dialog.isVisible():
                    dialog.reject()
        result = self.drive_dialogs(action, step)
        self.assertTrue(seen, 'Dialog did not enter an event loop')
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
                def inspect_shortcuts(dialog):
                    self.assert_above_owner(dialog,self.panel)
                    from yun_jin_hotkeys import ACTIONS
                    self.assertEqual(set(dialog.edits),set(ACTIONS))
                    dialog.reject()
                self.during_dialog(self.panel.show_shortcuts, inspect_shortcuts)
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
                # QMessageBox intentionally ignores window titles on macOS.
                # Identify the warning by the content and actions instead.
                self.assertEqual(box.text(), 'Scegli una data futura.')
                self.assertEqual(box.icon(), QMessageBox.Icon.Information)
                self.assertEqual(box.standardButtons(), QMessageBox.StandardButton.Ok)
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
        stages = []
        def advance(dialog):
            if isinstance(dialog, QFileDialog):
                if not stages:
                    stages.append('selected')
                    dialog.findChild(QLineEdit, 'fileNameEdit').setText(str(target))
                    dialog.accept()
                elif stages[-1] == 'declined':
                    stages.append('cancelled'); dialog.reject()
                else:
                    self.fail('File selection did not open the overwrite confirmation')
            elif isinstance(dialog, QMessageBox):
                self.assertEqual(stages, ['selected'])
                self.assert_above_owner(dialog, self.panel)
                self.assertEqual(dialog.text(), 'Il file esiste già. Sostituirlo?')
                self.assertEqual(dialog.icon(), QMessageBox.Icon.Question)
                self.assertEqual(dialog.standardButtons(),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                self.assertEqual(dialog.standardButton(dialog.defaultButton()), QMessageBox.StandardButton.No)
                stages.append('declined'); dialog.button(QMessageBox.StandardButton.No).click()
            else:
                self.fail('Unexpected dialog: ' + type(dialog).__name__)
        result = self.drive_dialogs(
            lambda: choose_files(self.panel, 'Backup', mode='save', filename=str(target)), advance)
        self.assertEqual(stages, ['selected', 'declined', 'cancelled'])
        self.assertEqual(result, []); self.assertEqual(target.read_bytes(), b'original')

    def test_driver_waits_for_deferred_focus(self):
        original = self.pet.focus_tool
        def delayed(widget):
            QTimer.singleShot(100, lambda: original(widget) if not sip.isdeleted(widget) else None)
        with patch.object(self.pet, 'focus_tool', side_effect=delayed):
            self.during_dialog(self.panel.show_shortcuts,
                               lambda box: self.assert_above_owner(box, self.panel))

    def test_driver_timeout_closes_unanswered_dialog(self):
        with self.assertRaisesRegex(AssertionError, 'Dialog timeout'):
            self.drive_dialogs(self.panel.show_shortcuts, lambda box: None, timeout=.1)
        self.assertIsNone(app.activeModalWidget())

    def test_driver_failure_also_closes_reopened_file_chooser(self):
        target = Path(self.tmp.name) / 'existing.zip'; target.write_bytes(b'original')
        def fail_in_confirmation(dialog):
            if isinstance(dialog, QFileDialog):
                dialog.findChild(QLineEdit, 'fileNameEdit').setText(str(target)); dialog.accept()
            else:
                self.fail('Deliberate inspection failure')
        with self.assertRaisesRegex(AssertionError, 'Deliberate inspection failure'):
            self.drive_dialogs(
                lambda: choose_files(self.panel, 'Backup', mode='save', filename=str(target)),
                fail_in_confirmation)
        self.assertIsNone(app.activeModalWidget())
        self.assertEqual(target.read_bytes(), b'original')

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

    def test_guide_data_folder_and_attachments_save_notes_and_hide_panel_on_success(self):
        path=Path(self.tmp.name)/'materiale.txt';path.write_text('materiale')
        folder=next(b for b in self.panel.findChildren(QPushButton) if b.text()=='Cartella dati')
        guide=Path(__file__).resolve().parents[1]/'Guida.pdf'
        for action,expected in [(self.pet.open_guide,guide),(folder.click,self.store.root),
                                (self.panel.open_material,path)]:
            with self.subTest(target=expected):
                self.pet.open_panel();self.panel.note_path=str(path)
                text='Da conservare: '+str(expected)
                self.panel.body.setPlainText(text);opened=[]
                def launch(url):
                    # Qt may terminate the process for an assertion escaping a
                    # clicked slot. Capture state here; assert after it returns.
                    opened.append((url.toLocalFile(),self.panel.dirty,self.store.note(self.panel.note_id)))
                    return True
                with patch('yun_jin_app.QDesktopServices.openUrl',side_effect=launch),patch.object(self.pet,'panel_closed') as closed:
                    action();self.assertFalse(self.panel.isVisible());closed.assert_called_once()
                self.assertEqual(len(opened),1)
                target,dirty,note=opened[0]
                self.assertEqual(Path(target).resolve(),expected.resolve())
                self.assertFalse(dirty);self.assertIsNotNone(note);self.assertEqual(note['body'],text)
                self.pet.open_panel();self.assertEqual(self.panel.body.toPlainText(),text)

    def test_failed_external_launch_or_save_keeps_the_editor_visible(self):
        self.panel.body.setPlainText('Non perdere questo testo')
        with patch('yun_jin_app.QDesktopServices.openUrl',return_value=False),patch('yun_jin_app.Messages.warning') as warning:
            self.pet.open_guide();warning.assert_called_once()
            self.assertTrue(self.panel.isVisible());self.assertEqual(self.panel.body.toPlainText(),'Non perdere questo testo')
        with patch.object(self.panel,'save_note',side_effect=OSError('Disco pieno')), \
                patch('yun_jin_app.QDesktopServices.openUrl') as launch,patch('yun_jin_app.Messages.warning') as warning:
            self.pet.open_guide();launch.assert_not_called();warning.assert_called_once()
            self.assertTrue(self.panel.isVisible())

    def test_chatgpt_and_weather_credit_links_yield_the_foreground(self):
        self.panel.body.setPlainText('Testo da spiegare')
        with patch('yun_jin_app.QDesktopServices.openUrl',return_value=True) as launch:
            self.panel.ask_ai();self.assertFalse(self.panel.isVisible())
            self.assertEqual(launch.call_args.args[0].toString(),'https://chatgpt.com/')
            self.assertIn('Testo da spiegare',QApplication.clipboard().text())
            self.pet.open_panel(tab=2)
            credit=next(label for label in self.panel.findChildren(QLabel) if 'href="https://open-meteo.com/' in label.text())
            self.assertFalse(credit.openExternalLinks());credit.linkActivated.emit('https://open-meteo.com/')
            self.assertFalse(self.panel.isVisible())
            self.assertEqual(launch.call_args.args[0].toString(),'https://open-meteo.com/')

    def test_release_links_hide_update_window_and_panel_but_reject_unsafe_links(self):
        manager=self.pet.updates
        manager.release=dict(version='1.3.1',url='https://github.com/PianothShaveck/yun-jin-companion/releases/tag/v1.3.1',
            notes='Una correzione.',automatic=True)
        manager.show_notes();dialog=manager.dialog
        with patch('yun_jin_app.QDesktopServices.openUrl',return_value=True) as launch:
            for url in ('file:///private/test','http://example.com','https://user:password@example.com'):
                dialog.open_link(QUrl(url))
            launch.assert_not_called();self.assertTrue(dialog.isVisible());self.assertTrue(self.panel.isVisible())
            dialog.web.click()
            self.assertEqual(launch.call_args.args[0].toString(),manager.release['url'])
            self.assertFalse(dialog.isVisible());self.assertFalse(self.panel.isVisible())
            self.pet.open_panel(tab=2);manager.show_notes()
            dialog.open_link(QUrl('https://github.com/PianothShaveck/yun-jin-companion'))
            self.assertFalse(dialog.isVisible());self.assertFalse(self.panel.isVisible())


if __name__ == '__main__':
    unittest.main(verbosity=2)
