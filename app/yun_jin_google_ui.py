# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional Calendar controls and one cancellable background worker."""
import threading
import time
from PyQt6 import sip
from PyQt6.QtCore import QObject, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget,
                            QTreeWidgetItem, QComboBox, QDialogButtonBox, QMenu)
from yun_jin_i18n import tr
from yun_jin_ui import STYLE, plain_label, button, icon_button
from yun_jin_dialogs import exec_dialog, show_dialog, owner_window


class GoogleSync(QObject):
    changed = pyqtSignal()
    browser_requested = pyqtSignal(str)
    completed = pyqtSignal(object)

    def __init__(self, pet):
        super().__init__(pet)
        self.pet, self.busy, self.status, self.failures = pet, False, '', 0
        self.needs_reconnect = False
        self.cancel = threading.Event()
        self.stopped = False
        self.pending = False
        self.suppress = False
        self.thread = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.VeryCoarseTimer)
        self.timer.timeout.connect(self.sync)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(5000)
        self.debounce.timeout.connect(self.sync)
        self.browser_requested.connect(lambda url: pet.open_external(QUrl(url)))
        self.completed.connect(self.finish)
        self.operation = ''
        # Agenda display/alert notifications are not local event edits. In
        # particular, a completed pull must never schedule another upload.
        if self.connected():
            self.timer.start(1500)

    def connected(self):
        return bool(self.pet.store.google.db.execute('SELECT 1 FROM google_accounts WHERE connected=1 LIMIT 1').fetchone())

    def local_changed(self):
        if not self.suppress and self.connected() and not self.stopped and not self.needs_reconnect:
            if self.busy:
                self.pending = True
            else:
                self.debounce.start()

    def sync(self):
        if self.connected():
            self.start('sync')

    def start(self, operation, argument=None):
        if self.busy or self.stopped:
            return False
        self.busy = True
        self.operation = operation
        self.timer.stop()
        self.debounce.stop()
        self.cancel = threading.Event()
        self.status = tr('Continua nel browser.') if operation == 'connect' else tr('Sincronizzazione…')
        self.changed.emit()
        root, cancel = self.pet.store.root, self.cancel
        profile = self.pet.store.preference('google_profile', '')
        def work():
            from yun_jin_data import Store
            from yun_jin_google_calendar import SyncEngine
            from yun_jin_google_auth import Vault, GoogleAPI, GoogleError, Cancelled, authorize, client_config
            store = None
            result = {'changed': False, 'error': '', 'retry': 0, 'cancelled': False, 'reauthorize': False}
            try:
                store = Store(root)
                state = store.google
                vault = Vault(profile)
                if operation == 'connect':
                    identity, credentials = authorize(client_config(argument), self.browser_requested.emit, cancel)
                    if cancel.is_set():
                        raise Cancelled()
                    vault.save(identity['sub'], credentials)
                    state.account(identity['sub'], identity['email'])
                    api = GoogleAPI(vault, identity['sub'], cancel)
                    state.set_calendars(identity['sub'], api.calendars())
                elif operation == 'disconnect':
                    # Cancellation happens before disconnect, never halfway through a write.
                    vault.delete(argument)
                    state.disconnect(argument)
                else:
                    for account in state.db.execute('SELECT id FROM google_accounts WHERE connected=1').fetchall():
                        api = GoogleAPI(vault, account['id'], cancel)
                        stamp_key = 'google_calendar_refresh_' + account['id']
                        if operation == 'refresh' or time.time() - store.preference(stamp_key, 0) >= 3600:
                            state.set_calendars(account['id'], api.calendars())
                            store.set_preference(stamp_key, time.time())
                        engine = SyncEngine(store, api, account['id'], cancel)
                        try:
                            engine.run()
                        finally:
                            # Earlier imports may have committed before a later
                            # request failed or was cancelled.
                            result['changed'] |= engine.changed
            except Cancelled:
                result['cancelled'] = True
            except Exception as exc:
                # Never expose response payloads, OAuth codes or credential errors.
                result['error'] = str(exc) if isinstance(exc, (GoogleError, ValueError)) else tr('Portachiavi o sincronizzazione non disponibili.')
                result['retry'] = getattr(exc, 'retry_after', 0)
                result['reauthorize'] = isinstance(exc, GoogleError) and exc.status == 401
            finally:
                if store is not None:
                    store.close()
                try:
                    self.completed.emit(result)
                except RuntimeError:
                    pass  # Application has already closed; the worker owns no GUI.
        self.thread = threading.Thread(target=work, name='YunJinCalendar', daemon=True)
        self.thread.start()
        return True

    def finish(self, result):
        self.busy = False
        self.thread = None
        if self.stopped:
            return
        if result['changed'] or self.operation in ('connect', 'disconnect'):
            self.pet.store.agenda.invalidate()
            callback = getattr(self.pet, 'refresh_agenda', None)
            if callable(callback):
                callback()
            self.suppress = True
            try:
                self.pet.agenda_changed.emit()
            finally:
                self.suppress = False
        if result['error']:
            self.failures += 1
            self.status = tr(result['error'])
            self.needs_reconnect |= result.get('reauthorize', False)
        else:
            self.failures = 0
            if not result['cancelled']:
                self.needs_reconnect = False
            if result['cancelled'] and self.operation == 'connect':
                self.status = tr('Collegamento annullato. Puoi riprovare quando vuoi.')
            else:
                self.status = ''
        self.changed.emit()
        if self.connected() and not self.needs_reconnect:
            delay = max(result['retry'], min(3600, 30 * 2**min(self.failures, 7))) if self.failures else 300
            self.timer.start(delay*1000)
            if self.pending and not self.failures:
                self.debounce.start()
        self.pending = False

    def shutdown(self):
        self.stopped = True
        self.cancel.set()
        self.timer.stop()
        self.debounce.stop()


class CalendarSettings(QDialog):
    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self.pet, self.sync = pet, pet.google_sync
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowTitle('Google Calendar')
        self.setStyleSheet(STYLE)
        self.resize(520, 130)
        self._has_accounts = None
        self._calendar_signature = None
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addStretch()
        self.close_button = icon_button('close', tr('Chiudi'), self.close, header)
        layout.addLayout(header)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemChanged.connect(self.select_calendar)
        layout.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.default_label = plain_label(tr('Nuovi impegni'))
        row.addWidget(self.default_label)
        self.default = QComboBox()
        self.default.currentIndexChanged.connect(self.set_default)
        row.addWidget(self.default, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        self.connect_button = button(tr('Collega account'), self.connect_account, row, role='primary')
        self.disconnect_button = button(tr('Account'), lambda: None, row)
        account_menu = QMenu(self.disconnect_button)
        account_menu.addAction(tr('Scollega questo dispositivo'), self.disconnect_account)
        account_menu.addAction(tr('Gestisci accesso Google'), lambda: pet.open_external(QUrl('https://myaccount.google.com/connections')))
        self.disconnect_button.setMenu(account_menu)
        row.addStretch()
        self.refresh_button = button(tr('Sincronizza'), lambda: self.sync.start('refresh'), row)
        layout.addLayout(row)
        self.status = plain_label('')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.conflicts_button = button(tr('Conflitti'), self.show_conflicts, layout)
        self.cancel_button = button(tr('Annulla'), lambda:self.sync.cancel.set(), layout)
        self.sync.changed.connect(self.refresh)
        self.tree.currentItemChanged.connect(self.update_buttons)
        self.refresh()

    def refresh(self):
        # Automatic work must not churn controls or keyboard focus while the
        # user is typing elsewhere. Manual operations still show progress.
        if self.sync.busy and self.sync.operation == 'sync':
            return
        state = self.pet.store.google
        accounts_rows = list(state.db.execute('SELECT id,email FROM google_accounts WHERE connected=1 ORDER BY email'))
        calendars = list(state.calendars())
        signature = (tuple((r['id'], r['email']) for r in accounts_rows),
                     tuple((c['account'], c['id'], c['name'], c['role'], c['selected'], c['email']) for c in calendars))
        if signature != self._calendar_signature:
            self.populate_calendars(accounts_rows, calendars)
            self._calendar_signature = signature
        self.default.blockSignals(True)
        self.default.setCurrentIndex(max(0, self.default.findData(self.pet.store.preference('google_default', None))))
        self.default.blockSignals(False)
        self.tree.setEnabled(not self.sync.busy)
        self.default.setEnabled(not self.sync.busy)
        self.status.setText(self.sync.status)
        self.status.setVisible(bool(self.sync.status))
        self.conflicts_button.setVisible(bool(state.conflicts()))
        self.conflicts_button.setEnabled(not self.sync.busy)
        self.cancel_button.setVisible(self.sync.busy)
        self.update_buttons()

    def populate_calendars(self, accounts_rows, calendars):
        self.tree.blockSignals(True)
        current = self.tree.currentItem()
        selected = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        self.tree.clear()
        accounts = {}
        for row in accounts_rows:
            item = QTreeWidgetItem([row['email']])
            item.setData(0, Qt.ItemDataRole.UserRole, [row['id'], None])
            self.tree.addTopLevelItem(item)
            accounts[row['id']] = item
            if [row['id'], None] == selected:
                self.tree.setCurrentItem(item)
        self.default.blockSignals(True)
        self.default.clear()
        self.default.addItem(tr('Solo su questo dispositivo'), None)
        for calendar in calendars:
            item = QTreeWidgetItem([calendar['name']])
            data = [calendar['account'], calendar['id']]
            item.setData(0, Qt.ItemDataRole.UserRole, data)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if calendar['selected'] else Qt.CheckState.Unchecked)
            if calendar['role'] not in ('writer', 'owner'):
                item.setToolTip(0, tr('Sola lettura'))
            accounts[calendar['account']].addChild(item)
            if data == selected:
                self.tree.setCurrentItem(item)
            if calendar['selected'] and calendar['role'] in ('writer', 'owner'):
                self.default.addItem(calendar['name'] + ' · ' + calendar['email'], data)
        self.tree.expandAll()
        has_accounts = bool(accounts)
        self.tree.setVisible(has_accounts)
        self.default.setVisible(has_accounts)
        self.default_label.setVisible(has_accounts)
        self.disconnect_button.setVisible(has_accounts)
        self.refresh_button.setVisible(has_accounts)
        if has_accounts != self._has_accounts:
            self.resize(520, 430 if has_accounts else 130)
            self._has_accounts = has_accounts
        self.tree.blockSignals(False)
        self.default.blockSignals(False)

    def closeEvent(self, event):
        if self.sync.busy and self.sync.operation == 'connect':
            self.sync.cancel.set()
        super().closeEvent(event)

    def update_buttons(self, *_):
        self.connect_button.setText(tr('Ricollega account') if self.sync.needs_reconnect else tr('Collega account'))
        self.connect_button.setEnabled(not self.sync.busy)
        self.disconnect_button.setEnabled(not self.sync.busy and self.tree.currentItem() is not None)
        self.refresh_button.setEnabled(not self.sync.busy and self.sync.connected() and not self.sync.needs_reconnect)

    def select_calendar(self, item, _):
        account, calendar = item.data(0, Qt.ItemDataRole.UserRole)
        if calendar:
            self.pet.store.google.select(account, calendar, item.checkState(0) == Qt.CheckState.Checked)
            self.refresh()
            self.sync.local_changed()

    def set_default(self, _):
        self.pet.store.set_preference('google_default', self.default.currentData())

    def connect_account(self):
        self.sync.start('connect')

    def disconnect_account(self):
        item = self.tree.currentItem()
        if item:
            self.sync.start('disconnect', item.data(0, Qt.ItemDataRole.UserRole)[0])

    def show_conflicts(self):
        rows = self.pet.store.google.conflicts()
        if not rows:
            return
        conflict = rows[0]
        dialog = QDialog(self)
        dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        dialog.setWindowTitle(tr('Conflitto'))
        dialog.setStyleSheet(STYLE)
        layout = QVBoxLayout(dialog)
        header = QHBoxLayout()
        header.addStretch()
        icon_button('close', tr('Chiudi'), dialog.reject, header)
        layout.addLayout(header)
        layout.addWidget(plain_label(conflict['title'] or tr('Impegno eliminato')))
        # Compare only actual differing values, and only while a conflict exists.
        import json
        from yun_jin_google_codec import FIELDS
        local = self.pet.store.google.snapshot(conflict['item'])
        remote = json.loads(conflict['remote'])
        for label, value in ((tr('Questo dispositivo'), local), ('Google Calendar', remote)):
            layout.addWidget(plain_label(label, 'section'))
            text = tr('Eliminato') if value is None else '\n'.join(str(value[k]) for k in ('title', 'start_local', 'end_local', 'details') if value.get(k))
            view = plain_label(text)
            view.setWordWrap(True)
            layout.addWidget(view)
        row = QHBoxLayout()
        def resolve(choice):
            self.pet.store.google.resolve(conflict['item'], choice)
            self.pet.agenda_changed.emit()
            self.sync.local_changed()
            dialog.accept()
            self.refresh()
        if not self.pet.store.google.readonly(conflict['item']):
            button(tr('Usa locale'), lambda: resolve('local'), row)
        button(tr('Usa Google'), lambda: resolve('remote'), row)
        button(tr('Conserva entrambi'), lambda: resolve('both'), row, role='primary')
        layout.addLayout(row)
        exec_dialog(dialog, self.pet)
        dialog.deleteLater()


def open_settings(pet, parent=None):
    dialog = getattr(pet, 'google_calendar_dialog', None)
    if dialog is not None and not sip.isdeleted(dialog):
        show_dialog(dialog, pet)
        return dialog
    dialog = CalendarSettings(pet, owner_window(parent or pet))
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    pet.google_calendar_dialog = dialog
    def release(*_):
        if pet.google_sync.busy and pet.google_sync.operation == 'connect':
            pet.google_sync.cancel.set()
        if getattr(pet, 'google_calendar_dialog', None) is dialog:
            pet.google_calendar_dialog = None
    dialog.finished.connect(release)
    show_dialog(dialog, pet)
    if not pet.google_sync.connected() or pet.google_sync.needs_reconnect:
        dialog.connect_account()
    return dialog


def destination_picker(pet, layout, event=None):
    state = pet.store.google
    calendars = state.calendars(selected=True)
    link = state.link(event['id']) if event else None
    if not calendars and not link:
        return None
    picker = QComboBox()
    picker.setAccessibleName(tr('Calendario'))
    picker.addItem(tr('Solo su questo dispositivo'), None)
    for c in calendars:
        if c['role'] in ('writer', 'owner') or link and (link['account'], link['calendar']) == (c['account'], c['id']):
            picker.addItem(c['name'] + ' · ' + c['email'], [c['account'], c['id']])
    target = [link['account'], link['calendar']] if link else None if event else pet.store.preference('google_default', None)
    if link and picker.findData(target) < 0:
        picker.addItem('Google Calendar', target)
    picker.setCurrentIndex(max(0, picker.findData(target)))
    picker.setEnabled(link is None)
    layout.addWidget(picker)
    return picker
