"""Optional controls stay hidden locally; synchronization never polls when off."""
import sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch,Mock
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtCore import pyqtSignal,Qt,QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QWidget,QDialogButtonBox,QLabel,QLineEdit,QVBoxLayout
from yun_jin_data import Store
from yun_jin_google_ui import GoogleSync,CalendarSettings,open_settings
from yun_jin_calendar_ui import EventDialog,CalendarPanel,notify_changed
from yun_jin_agenda_service import AgendaService
app=QApplication.instance() or QApplication([])
class Pet(QWidget):
    agenda_changed=pyqtSignal()
    def __init__(self,store):super().__init__();self.store=store;self.closing=False;self.urls=[]
    def open_external(self,url):self.urls.append(url.toString())
    def focus_tool(self,widget):pass

class GoogleUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.pet=Pet(self.store)
        self.pet.google_sync=GoogleSync(self.pet);self.widgets=[]
    def tearDown(self):
        self.pet.google_sync.shutdown()
        for w in self.widgets:w.close();w.deleteLater()
        self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()
    def keep(self,w):self.widgets.append(w);return w
    def connected(self,role='owner'):
        self.store.google.account('a','test@example.test')
        self.store.google.set_calendars('a',[dict(id='c',summary='Lessons',accessRole=role,timeZone='Europe/Rome')])
        self.store.google.select('a','c',True)
    def test_local_profile_has_no_destination_or_sync_timer(self):
        event=self.keep(EventDialog(self.pet))
        self.assertIsNone(event.destination)
        self.assertFalse(self.pet.google_sync.timer.isActive())
        self.pet.agenda_changed.emit()
        self.assertFalse(self.pet.google_sync.debounce.isActive())
    def test_destination_saved_and_default_does_not_upload_existing_local_items(self):
        self.connected();self.store.set_preference('google_default',['a','c'])
        event=self.keep(EventDialog(self.pet));event.title.setText('Lesson');event.save()
        self.assertEqual(self.store.google.link(event.saved_id)['calendar'],'c')
        self.assertTrue(self.pet.google_sync.debounce.isActive())
        local=self.store.agenda.save_event('Local','2027-02-01T09:00:00')
        edit=self.keep(EventDialog(self.pet,event=self.store.agenda.get(local)))
        self.assertIsNone(edit.destination.currentData())
    def test_readonly_editor_cannot_save(self):
        self.connected();item=self.store.agenda.save_event('Remote','2027-02-01T09:00:00');self.store.google.assign(item,'a','c')
        self.store.google.set_calendars('a',[dict(id='c',summary='Lessons',accessRole='reader')])
        event=self.keep(EventDialog(self.pet,event=self.store.agenda.get(item)))
        self.assertTrue(event.google_readonly)
        self.assertTrue(event.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).isHidden())
        event.title.setText('Attempt');event.save()
        self.assertEqual(self.store.agenda.get(item)['title'],'Remote')
    def test_debounce_coalesces_changes_and_shutdown_cancels(self):
        self.connected()
        for _ in range(5):self.pet.google_sync.local_changed()
        self.assertTrue(self.pet.google_sync.debounce.isActive())
        self.assertEqual(self.pet.google_sync.debounce.interval(),5000)
        self.pet.google_sync.shutdown()
        self.assertFalse(self.pet.google_sync.debounce.isActive());self.assertTrue(self.pet.google_sync.cancel.is_set())

    def test_idle_sync_and_alert_ticks_do_not_schedule_another_request_or_rebuild_agenda(self):
        self.connected();sync=self.pet.google_sync
        self.pet.speech=SimpleNamespace(current_tag=None)
        service=AgendaService(self.pet)
        self.pet.refresh_agenda=service.refresh
        service.tick()  # Establish the normal idle scheduler state.
        revision=self.store.agenda.revision
        with patch.object(self.pet,'refresh_agenda',wraps=service.refresh) as refresh, \
             patch.object(self.store.agenda,'invalidate',wraps=self.store.agenda.invalidate) as invalidate, \
             patch.object(self.store.agenda,'occurrences',wraps=self.store.agenda.occurrences) as occurrences:
            for _ in range(3):
                sync.busy=True;sync.operation='sync'
                sync.finish(dict(changed=False,error='',retry=0,cancelled=False))
                for _ in range(5):service.tick()
                self.assertFalse(sync.debounce.isActive())
                self.assertFalse(sync.pending)
                self.assertEqual(sync.timer.interval(),300000)
                self.assertEqual(sync.timer.timerType(),Qt.TimerType.VeryCoarseTimer)
            refresh.assert_not_called();invalidate.assert_not_called();occurrences.assert_not_called()
        self.assertEqual(self.store.agenda.revision,revision)
        service.shutdown()

    def test_remote_import_refreshes_visible_events_without_feedback_upload(self):
        self.connected();sync=self.pet.google_sync
        self.pet.speech=SimpleNamespace(current_tag=None)
        service=AgendaService(self.pet);self.pet.refresh_agenda=service.refresh
        panel=self.keep(CalendarPanel(self.pet));panel.show();app.processEvents()
        from datetime import date
        other=Store(self.tmp.name)
        try:other.agenda.save_event('Phone import',date.today().isoformat()+'T09:00:00')
        finally:other.close()
        sync.operation='sync';sync.busy=True
        sync.finish(dict(changed=True,error='',retry=0,cancelled=False))
        for _ in range(5):service.tick()
        self.assertIn('Phone import',[row['title'] for row in panel.rows])
        self.assertFalse(sync.debounce.isActive());self.assertFalse(sync.pending)
        service.shutdown()

    def test_only_linked_edits_schedule_upload_not_local_items_alarms_or_alert_signals(self):
        self.connected();sync=self.pet.google_sync
        item=self.store.agenda.save_event('Local','2032-03-05T09:00:00')
        notify_changed(self.pet,item);self.pet.agenda_changed.emit()
        self.assertFalse(sync.debounce.isActive())
        self.store.google.assign(item,'a','c')
        notify_changed(self.pet,item)
        self.assertTrue(sync.debounce.isActive());sync.debounce.stop()
        notify_changed(self.pet);self.pet.agenda_changed.emit()
        self.assertFalse(sync.debounce.isActive())
        self.store.agenda.delete(item);notify_changed(self.pet,item)
        self.assertTrue(sync.debounce.isActive())  # Deletion retains its outbox link.

    def test_linked_edit_during_worker_schedules_one_followup(self):
        self.connected();sync=self.pet.google_sync
        item=self.store.agenda.save_event('Edit while syncing','2032-03-05T09:00:00')
        self.store.google.assign(item,'a','c');sync.busy=True;sync.operation='sync'
        for _ in range(3):notify_changed(self.pet,item)
        self.assertTrue(sync.pending);self.assertFalse(sync.debounce.isActive())
        sync.finish(dict(changed=False,error='',retry=0,cancelled=False))
        self.assertFalse(sync.pending);self.assertTrue(sync.debounce.isActive())
        self.assertEqual(sync.timer.interval(),300000)

    def test_partial_import_before_network_failure_still_refreshes_local_cache(self):
        self.connected();sync=self.pet.google_sync
        from yun_jin_google_auth import GoogleError
        results=[];sync.completed.connect(results.append)
        self.store.set_preference('google_calendar_refresh_a',__import__('time').time())
        engine=Mock(changed=True);engine.run.side_effect=GoogleError(503)
        with patch('yun_jin_google_auth.Vault'),patch('yun_jin_google_auth.GoogleAPI'), \
             patch('yun_jin_google_calendar.SyncEngine',return_value=engine), \
             patch('yun_jin_google_ui.threading.Thread') as thread:
            thread.side_effect=lambda **kw:SimpleNamespace(start=kw['target'])
            self.assertTrue(sync.start('sync'))
        self.assertTrue(results[0]['changed']);self.assertTrue(results[0]['error'])
        self.assertEqual(sync.timer.interval(),60000)
        self.assertFalse(sync.debounce.isActive())
    def test_settings_show_calendar_accounts_without_redundant_status(self):
        self.connected();dialog=self.keep(CalendarSettings(self.pet))
        self.assertEqual(dialog.tree.topLevelItemCount(),1)
        self.assertEqual(dialog.tree.topLevelItem(0).childCount(),1)
        self.assertEqual(dialog.default.count(),2)
        self.assertTrue(dialog.status.isHidden());self.assertTrue(dialog.conflicts_button.isHidden())
        actions=dialog.disconnect_button.menu().actions()
        self.assertEqual(len(actions),2)
        actions[1].trigger()
        self.assertEqual(self.pet.urls,['https://myaccount.google.com/connections'])

    def test_new_profile_has_no_empty_list_or_permanent_explanatory_text(self):
        dialog=self.keep(CalendarSettings(self.pet))
        self.assertEqual([label.text() for label in dialog.findChildren(QLabel)
                          if not label.isHidden() and label.text()],[])
        for control in (dialog.tree,dialog.default,dialog.default_label,
                        dialog.disconnect_button,dialog.refresh_button):
            self.assertTrue(control.isHidden())
        # The normal user path must never ask for a developer file.
        with patch('yun_jin_dialogs.choose_files',side_effect=AssertionError('No file picker during sign-in')), \
             patch.object(self.pet.google_sync,'start',return_value=True) as start:
            dialog.connect_button.click()
        start.assert_called_once_with('connect')
        self.assertFalse(self.pet.google_sync.timer.isActive())

    def test_calendar_has_a_visible_entry_to_the_same_account_controls(self):
        panel=self.keep(CalendarPanel(self.pet))
        self.assertEqual(panel.google_button.text(),'Collega Google Calendar')
        with patch('yun_jin_google_ui.open_settings') as open_settings:
            panel.google_button.click()
        open_settings.assert_called_once_with(self.pet,panel)

    def test_account_controls_appear_after_connect_and_hide_after_disconnect(self):
        dialog=self.keep(CalendarSettings(self.pet))
        self.connected();self.pet.google_sync.changed.emit()
        self.assertFalse(dialog.tree.isHidden())
        self.assertFalse(dialog.default.isHidden())
        self.store.google.disconnect('a');self.pet.google_sync.changed.emit()
        self.assertTrue(dialog.tree.isHidden())

    def test_calendar_entry_starts_browser_flow_without_an_extra_connect_step(self):
        with patch.object(self.pet.google_sync,'start',return_value=True) as start:
            open_settings(self.pet,self.pet)
        start.assert_called_once_with('connect')
        self.connected()
        with patch.object(self.pet.google_sync,'start',return_value=True) as start:
            open_settings(self.pet,self.pet)
        start.assert_not_called()

    def test_accounts_window_is_modeless_reused_and_mouse_closable_without_titlebar(self):
        self.connected();self.pet.show()
        dialog=open_settings(self.pet,self.pet)
        self.assertIs(open_settings(self.pet,self.pet),dialog)
        app.processEvents()
        self.assertTrue(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertEqual(dialog.windowModality(),Qt.WindowModality.NonModal)
        self.assertIsNone(app.activeModalWidget())
        self.assertTrue(self.pet.isEnabled())
        self.assertTrue(dialog.close_button.isVisible());self.assertTrue(dialog.close_button.isEnabled())
        self.assertEqual(dialog.close_button.accessibleName(),'Chiudi')
        QTest.mouseClick(dialog.close_button,Qt.MouseButton.LeftButton)
        self.assertFalse(dialog.isVisible())
        self.assertIsNone(self.pet.google_calendar_dialog)
        replacement=open_settings(self.pet,self.pet)
        self.assertIsNot(replacement,dialog)
        replacement.close()

    def test_automatic_sync_preserves_other_window_typing_and_unchanged_tree_items(self):
        self.connected()
        panel=self.keep(CalendarPanel(self.pet));panel.show()
        dialog=open_settings(self.pet,panel);app.processEvents()
        original=dialog.tree.topLevelItem(0)
        external=self.keep(QWidget());layout=QVBoxLayout(external);edit=QLineEdit();layout.addWidget(edit)
        external.show();external.activateWindow();edit.setFocus();app.processEvents()
        self.assertIs(app.focusWidget(),edit)
        with patch.object(self.pet,'focus_tool') as focus, \
             patch('yun_jin_google_ui.show_dialog') as show, \
             patch('yun_jin_google_ui.threading.Thread'):
            for _ in range(3):
                self.assertTrue(self.pet.google_sync.start('sync'))
                self.pet.google_sync.finish(dict(changed=False,error='',retry=0,cancelled=False))
                app.processEvents()
                self.assertIs(app.focusWidget(),edit)
                self.assertIs(dialog.tree.topLevelItem(0),original)
                self.assertIsNone(app.activeModalWidget())
                QTest.keyClicks(edit,'abc')
            focus.assert_not_called();show.assert_not_called()
        self.assertEqual(edit.text(),'abcabcabc')
        dialog.close()

    def test_mouse_close_cancels_pending_signin_but_leaves_background_sync_running(self):
        for operation in ('connect','sync'):
            with self.subTest(operation=operation):
                sync=self.pet.google_sync;sync.cancel.clear();sync.busy=True;sync.operation=operation
                dialog=self.keep(CalendarSettings(self.pet));dialog.show();app.processEvents()
                QTest.mouseClick(dialog.close_button,Qt.MouseButton.LeftButton)
                self.assertFalse(dialog.isVisible())
                self.assertEqual(sync.cancel.is_set(),operation=='connect')
                sync.busy=False

    def test_conflict_window_can_be_mouse_closed_without_resolving_or_deleting(self):
        item=self.store.agenda.save_event('Keep this event','2027-02-01T09:00:00')
        before=self.store.google.snapshot(item);dialog=self.keep(CalendarSettings(self.pet));errors=[]
        conflict={'item':item,'title':'Keep this event','remote':json.dumps(before)}
        def dismiss():
            modal=app.activeModalWidget()
            try:
                close=next(b for b in modal.findChildren(QWidget) if b.accessibleName()=='Chiudi')
                self.assertTrue(close.isVisible());self.assertTrue(close.isEnabled())
                QTest.mouseClick(close,Qt.MouseButton.LeftButton)
            except Exception as exc:
                errors.append(exc)
                if modal:modal.reject()
        with patch.object(self.store.google,'conflicts',return_value=[conflict]), \
             patch.object(self.store.google,'resolve') as resolve:
            QTimer.singleShot(0,dismiss);dialog.show_conflicts()
            resolve.assert_not_called()
        if errors:raise errors[0]
        self.assertEqual(self.store.google.snapshot(item),before)

    def test_cancelled_connection_has_an_explanation_and_can_be_retried(self):
        sync=self.pet.google_sync
        sync.operation='connect';sync.busy=True
        sync.finish(dict(changed=False,error='',retry=0,cancelled=True))
        self.assertTrue(sync.status)
        self.assertNotEqual(sync.status,'Sincronizzato')
        self.assertFalse(sync.busy)
        self.assertFalse(sync.timer.isActive())

    def test_expired_authorization_is_actionable_without_deleting_local_changes(self):
        self.connected();item=self.store.agenda.save_event('Pending lesson','2027-02-01T09:00:00')
        self.store.google.assign(item,'a','c')
        before=self.store.google.snapshot(item)
        dialog=self.keep(CalendarSettings(self.pet));panel=self.keep(CalendarPanel(self.pet))
        sync=self.pet.google_sync;sync.busy=True;sync.operation='sync'
        sync.finish(dict(changed=False,error='Ricollega Google Calendar.',retry=0,cancelled=False,reauthorize=True))
        self.assertTrue(sync.needs_reconnect)
        self.assertFalse(sync.timer.isActive())
        self.assertEqual(dialog.connect_button.text(),'Ricollega account')
        self.assertEqual(panel.google_button.text(),'Ricollega Google Calendar')
        self.pet.agenda_changed.emit()
        self.assertFalse(sync.debounce.isActive())
        self.assertFalse(dialog.refresh_button.isEnabled())
        self.assertEqual(self.store.google.snapshot(item),before)
        sync.finish(dict(changed=False,error='',retry=0,cancelled=False))
        self.assertFalse(sync.needs_reconnect)
        self.assertEqual(dialog.connect_button.text(),'Collega account')
        self.assertEqual(panel.google_button.text(),'Google Calendar')
if __name__=='__main__':unittest.main()
