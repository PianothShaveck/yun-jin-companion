# SPDX-License-Identifier: GPL-3.0-or-later
"""Nonblocking update checks, readable release notes, and an explicit restart."""
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid
from PyQt6.QtCore import QObject, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QTextDocument
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
                            QPushButton, QProgressBar, QMessageBox, QApplication)
from yun_jin_platform import VERSION
from yun_jin_core import BASE
from yun_jin_ui import STYLE
from yun_jin_dialogs import message, owner_window, show_dialog
import yun_jin_update as engine


class LocalNotes(QTextBrowser):
    def loadResource(self, kind, name):
        # Release Markdown may contain remote images: reading notes must never
        # silently load trackers, local files, or execute external content.
        return None


class UpdateDialog(QDialog):
    def __init__(self, manager):
        super().__init__(owner_window(manager.pet), Qt.WindowType.Tool)
        self.manager = manager
        self.setWindowTitle('Yun Jin · Aggiornamento')
        self.setStyleSheet(STYLE)
        self.setWindowIcon(manager.pet.windowIcon())
        self.resize(610, 560)
        layout = QVBoxLayout(self); layout.setContentsMargins(22, 20, 22, 20); layout.setSpacing(12)
        self.title = QLabel(); self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setStyleSheet('font-size: 19px; font-weight: 600;')
        layout.addWidget(self.title)
        self.summary = QLabel(); self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(self.summary)
        self.notes = LocalNotes(); self.notes.setOpenLinks(False); self.notes.setOpenExternalLinks(False)
        self.notes.anchorClicked.connect(self.open_link)
        layout.addWidget(self.notes, 1)
        self.progress = QProgressBar(); self.progress.hide(); layout.addWidget(self.progress)
        self.status = QLabel(); self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True); layout.addWidget(self.status)
        row = QHBoxLayout(); self.web = QPushButton('Apri release su GitHub')
        self.web.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.manager.release['url'])))
        row.addWidget(self.web); row.addStretch()
        self.later = QPushButton('Più tardi'); self.later.clicked.connect(self.close); row.addWidget(self.later)
        self.skip = QPushButton('Salta questa versione'); self.skip.clicked.connect(manager.skip_version)
        layout.addWidget(self.skip, alignment=Qt.AlignmentFlag.AlignRight)
        self.install = QPushButton('Aggiorna e riavvia'); self.install.setProperty('role', 'primary')
        self.install.clicked.connect(manager.install); row.addWidget(self.install); layout.addLayout(row)

    def open_link(self, url):
        if url.scheme() == 'https' and not url.userName() and not url.password():
            QDesktopServices.openUrl(url)

    def refresh(self):
        release = self.manager.release
        self.title.setText('È disponibile Yun Jin ' + release['version'])
        self.summary.setText('Versione attuale: ' + VERSION + '. Leggi le novità prima di aggiornare.\n'
                             'Yun Jin salverà gli appunti, installerà l’aggiornamento e si riaprirà.')
        self.notes.document().setMarkdown(release['notes'], QTextDocument.MarkdownFeature.MarkdownNoHTML)
        self.status.setText(release.get('reason', ''))
        self.install.setEnabled(release['automatic'] and not self.manager.busy)
        self.later.setEnabled(not self.manager.installing)
        self.skip.setEnabled(not self.manager.installing)
        self.progress.setVisible(self.manager.installing)

    def closeEvent(self, event):
        if self.manager.installing:
            event.ignore(); return
        self.manager.snooze_until = time.time() + engine.INTERVAL
        event.accept()


class Updates(QObject):
    status_changed = pyqtSignal(str)
    available_changed = pyqtSignal()
    checked = pyqtSignal(object, str, bool)
    downloaded = pyqtSignal(str, str)
    progress = pyqtSignal(int)

    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.enabled = bool(pet.store.preference('updates_enabled', True))
        self.busy = False; self.installing = False
        self.release = None; self.dialog = None
        self.status = 'Versione ' + VERSION
        self.snooze_until = 0
        self.last_prompt = ''
        self.staged = None
        self.cache = pet.store.root / 'updates'
        self.checked.connect(self.on_checked); self.downloaded.connect(self.on_downloaded)
        self.progress.connect(self.on_progress)
        self.timer = QTimer(self); self.timer.setInterval(engine.INTERVAL * 1000)
        self.timer.timeout.connect(self.check)
        self.initial = QTimer(self); self.initial.setSingleShot(True)
        self.initial.timeout.connect(self.check)
        self.offer = QTimer(self); self.offer.setInterval(30000); self.offer.timeout.connect(self.maybe_offer)
        self.worker_timer = QTimer(self); self.worker_timer.setInterval(100)
        self.worker_timer.timeout.connect(self.worker_ready)
        self.worker_process = None
        if self.enabled:
            self.timer.start(); self.initial.start(30000)
        self.show_previous_result()

    def set_status(self, text):
        self.status = text; self.status_changed.emit(text)

    def message(self, icon, title, text, buttons=QMessageBox.StandardButton.Ok,
                default=QMessageBox.StandardButton.Ok, parent=None):
        return message(parent if parent is not None else self.pet, icon, title, text, buttons, default)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.pet.store.set_preference('updates_enabled', self.enabled)
        if self.enabled:
            self.timer.start(); self.initial.start(1000)
        else:
            self.timer.stop(); self.initial.stop(); self.offer.stop()
        self.set_status('Controllo automatico attivo ogni 2 ore.' if self.enabled else
                        'Controllo automatico disattivato. Puoi verificare quando vuoi.')

    def check(self, manual=False):
        if self.busy or self.pet.closing or (not manual and not self.enabled):
            return
        self.busy = True
        self.set_status('Controllo aggiornamenti…')
        self.available_changed.emit()
        def run():
            try:
                self.checked.emit(engine.check_release(VERSION), '', manual)
            except Exception as exc:
                self.checked.emit(None, str(exc), manual)
        threading.Thread(target=run, daemon=True, name='yun-jin-check').start()

    def on_checked(self, release, error, manual):
        self.busy = False
        if self.pet.closing:
            return
        if error:
            logging.warning('Update check: %s', error)
            self.set_status('Controllo non riuscito. Riprova quando la connessione è disponibile.')
            if manual:
                self.message(QMessageBox.Icon.Information, 'Aggiornamenti', self.status + '\n\n' + error)
        elif release is None:
            self.set_status('Yun Jin ' + VERSION + ' è aggiornata. Ultimo controllo: ' + time.strftime('%H:%M'))
            if manual:
                self.message(QMessageBox.Icon.Information, 'Aggiornamenti', self.status)
        else:
            self.release = release
            self.set_status('Disponibile la versione ' + release['version'] + '. Leggi le novità prima di aggiornare.')
            if manual:
                self.show_notes()
            elif self.enabled and release['version'] != self.pet.store.preference('updates_skip_version', ''):
                self.offer.start(); self.maybe_offer()
        self.available_changed.emit()

    def activities_running(self):
        p = self.pet
        return (QApplication.activeModalWidget() is not None or p.speech.busy or p.metronome.running or p.stopwatch.running or p.focus_active()
                or p.menu_open or p.drag_anchor is not None or p.reminder_dialog is not None)

    def skip_version(self):
        if self.release and not self.installing:
            self.pet.store.set_preference('updates_skip_version', self.release['version'])
            self.offer.stop()
            self.set_status('Versione ' + self.release['version'] + ' saltata. Cercherò le successive.')
            if self.dialog:
                self.dialog.hide()

    def maybe_offer(self):
        if not self.enabled or not self.release or self.pet.closing:
            self.offer.stop(); return
        if self.busy or time.time() < self.snooze_until or self.activities_running():
            return
        if self.dialog and self.dialog.isVisible():
            return
        # Show quietly once; Più tardi permits a reminder at the next 2-hour check.
        self.offer.stop()
        self.show_notes(quiet=True)

    def show_notes(self, quiet=False):
        if not self.release:
            self.check(manual=True); return
        if self.dialog is None:
            self.dialog = UpdateDialog(self)
        owner = owner_window(self.pet)
        if self.dialog.parentWidget() is not owner:
            self.dialog.setParent(owner, self.dialog.windowFlags())
        self.dialog.refresh()
        show_dialog(self.dialog, self.pet, quiet=quiet)

    def install(self):
        if self.busy or not self.release or not self.release['automatic']:
            return
        if self.activities_running():
            answer = self.message(QMessageBox.Icon.Question, 'Attività in corso',
                'L’aggiornamento chiuderà Yun Jin e interromperà l’attività in corso. Aggiornare adesso?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No, parent=self.dialog)
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            if self.pet.panel:
                self.pet.panel.save_note()
            # Check the real destination before downloading; never fall back to
            # a different installation folder or ask for administrator access.
            probe = BASE / ('.update-write-' + uuid.uuid4().hex)
            probe.write_text('', encoding='utf-8'); probe.unlink()
            probe = BASE.parent / ('.update-write-' + uuid.uuid4().hex)
            probe.write_text('', encoding='utf-8'); probe.unlink()
        except Exception as exc:
            self.message(QMessageBox.Icon.Warning, 'Aggiornamento non avviato', str(exc), parent=self.dialog); return
        self.busy = self.installing = True
        self.dialog.refresh(); self.dialog.status.setText('Download e verifica del pacchetto…')
        self.set_status('Download dell’aggiornamento…'); self.available_changed.emit()
        release = dict(self.release)
        def run():
            try:
                source = engine.prepare_update(release, self.cache, self.progress.emit)
                self.downloaded.emit(source, '')
            except Exception as exc:
                self.downloaded.emit('', str(exc))
        threading.Thread(target=run, daemon=True, name='yun-jin-download').start()

    def on_progress(self, value):
        if self.dialog:
            self.dialog.progress.setValue(value)

    def on_downloaded(self, source, error):
        if self.pet.closing:
            return
        if error:
            self.install_failed(error); return
        try:
            source = Path(source)
            work = source.parent.parent
            self.staged = work
            helper = work / 'worker.py'
            shutil.copy2(Path(engine.__file__), helper)
            executable = Path(sys.executable)
            # pythonw is suitable for both the helper and the restarted app.
            plan = dict(source=str(source), app_dir=str(BASE), executable=str(executable),
                        version=self.release['version'], lock=str(self.pet.store.root / 'companion.lock'),
                        token=uuid.uuid4().hex)
            engine.write_json(work / 'plan.json', plan)
            engine.write_json(self.cache / 'pending.json', {'work': str(work), 'app_dir': str(BASE)})
            kwargs = {'cwd': str(work), 'stdin': subprocess.DEVNULL,
                      'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
            if sys.platform == 'win32':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs['start_new_session'] = True
            self.worker_process = subprocess.Popen([str(executable), str(helper), '--worker', str(work / 'plan.json')], **kwargs)
            self.worker_deadline = time.monotonic() + 15
            self.worker_timer.start()
            self.dialog.status.setText('Preparazione del riavvio…')
        except Exception as exc:
            self.install_failed(str(exc))

    def worker_ready(self):
        if (self.staged / 'worker-ready.json').is_file():
            self.worker_timer.stop()
            # closeEvent saves again after the download, so edits made while
            # downloading are included. It may refuse closure if saving fails.
            if not self.pet.close():
                (self.staged / 'cancel').touch()
                self.install_failed('Non è stato possibile salvare e chiudere Yun Jin. Riprova dopo aver salvato gli appunti.')
        elif self.worker_process.poll() is not None or time.monotonic() > self.worker_deadline:
            self.worker_timer.stop()
            (self.staged / 'cancel').touch()
            self.install_failed('Il programma di aggiornamento non è partito. Nessun file modificato.')

    def install_failed(self, text):
        self.busy = self.installing = False
        self.set_status('Aggiornamento non installato.')
        if self.dialog:
            self.dialog.refresh(); self.dialog.status.setText(text)
        self.available_changed.emit()
        logging.warning('Update not installed: %s', text)

    def show_previous_result(self):
        path = os.environ.pop('YUN_JIN_UPDATE_RESULT', '')
        if not path:
            return
        try:
            result = json.loads(Path(path).read_text(encoding='utf-8'))
            if result.get('ok'):
                self.set_status('Aggiornamento a ' + VERSION + ' completato.')
            else:
                text = result.get('message', 'Aggiornamento non completato.')
                QTimer.singleShot(1000, lambda: self.message(QMessageBox.Icon.Warning, 'Aggiornamento', text))
        except (OSError, ValueError):
            logging.exception('Reading update result')

    def shutdown(self):
        for timer in (self.timer, self.initial, self.offer):
            timer.stop()
        if self.dialog:
            self.dialog.hide()
