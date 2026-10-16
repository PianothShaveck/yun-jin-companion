"""Alarm delivery, recovery, voice independence and optional global shortcuts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QApplication,QWidget,QDialog
from yun_jin_data import Store
from yun_jin_agenda_service import AgendaService
from yun_jin_hotkeys import Hotkeys,DEFAULTS,IDENTS,ACTIONS,GROUPS

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class Pet(QWidget):
    agenda_changed=pyqtSignal()
    def __init__(self,store):
        super().__init__();self.store=store;self.closing=False
        self.effect=Mock();self.sound=SimpleNamespace(enabled=True,volume=.28,quiet_until=0,
            prepare=Mock(),effect_type=Mock(return_value=self.effect),play=Mock())
        self.speech=SimpleNamespace(speak=Mock(),stop=Mock(),current_tag=None,enabled=True)
        self.queue_feedback=Mock();self.open_panel=Mock()
    def notification_position(self,widget):return (5,5)


class AlarmDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.pet=Pet(self.store)
        self.service=AgendaService(self.pet)
        self.now=datetime(2032,3,5,8).timestamp()
    def tearDown(self):
        self.service.shutdown()
        if self.service.card:self.service.card.deleteLater()
        self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()
    def alarm(self,**extra):
        return self.store.agenda.save_alarm('Alzati',clock='08:00',on_date='2032-03-05',now=self.now-120,**extra)
    def tick(self,now=None):
        with patch('time.time',return_value=self.now if now is None else now):self.service.tick()

    def test_alarm_rings_once_stops_snoozes_and_rings_again(self):
        ident=self.alarm();self.tick();self.assertTrue(self.service.card.isVisible())
        self.pet.effect.play.assert_called_once();self.pet.speech.speak.assert_called_once()
        self.assertFalse(self.store.agenda.get(ident)['enabled'])
        self.tick();self.pet.effect.play.assert_called_once()
        alert=self.service.card.alert['id']
        with patch('time.time',return_value=self.now):self.service.snooze(alert)
        self.assertFalse(self.service.card.isVisible());self.assertFalse(self.service.ringing)
        self.tick(self.now+599);self.pet.effect.play.assert_called_once()
        self.tick(self.now+600);self.assertEqual(self.pet.effect.play.call_count,2)
        self.service.dismiss(alert);self.assertFalse(self.service.card.isVisible())
        self.assertFalse(self.store.agenda.pending_alerts())

    def test_restart_restores_pending_card_without_repeating_sound_or_speech(self):
        self.alarm();self.tick();self.service.shutdown();self.service.card.deleteLater()
        self.store._agenda=None;self.pet.effect.reset_mock();self.pet.speech.speak.reset_mock()
        self.service=AgendaService(self.pet);self.tick(self.now+20)
        self.assertTrue(self.service.card.isVisible());self.pet.effect.play.assert_not_called()
        self.pet.speech.speak.assert_not_called()

    def test_dismiss_one_of_two_due_alarms_keeps_the_other_visible_and_ringing(self):
        self.alarm();self.alarm();self.tick();self.assertEqual(len(self.service.ringing),2)
        self.service.dismiss(self.service.card.alert['id'])
        self.assertEqual(len(self.service.ringing),1);self.assertTrue(self.service.card.isVisible())
        self.service.card.dismiss();self.assertFalse(self.service.card.isVisible())

    def test_muted_audio_keeps_alert_visible_and_voice_setting_is_independent(self):
        self.alarm(voice=False);self.pet.sound.enabled=False;self.tick()
        self.assertTrue(self.service.card.isVisible());self.pet.sound.prepare.assert_not_called()
        self.pet.speech.speak.assert_not_called()

    def test_event_does_not_loop_audio_and_literal_title_is_preserved(self):
        self.store.agenda.save_event('<b>中文</b>', '2032-03-05T08:00:00','2032-03-05T09:00:00',
                                    reminder_minutes=0,now=self.now-120)
        self.tick();self.pet.sound.play.assert_called_once_with('reminder')
        self.pet.effect.play.assert_not_called();self.assertEqual(self.service.card.title.text(),'<b>中文</b>')
        self.assertEqual(self.pet.speech.speak.call_args.kwargs['category'],'calendar')

    def test_audio_is_bounded_and_global_sound_mute_stops_an_active_ring(self):
        self.alarm();self.tick();self.assertTrue(self.service.ringing)
        self.service.ring_until=0;self.tick();self.assertFalse(self.service.ringing)
        self.service.start_ring([self.service.card.alert]);self.pet.sound.enabled=False
        self.tick();self.assertFalse(self.service.ringing);self.assertTrue(self.service.card.isVisible())

    def test_shutdown_and_storage_error_do_not_escape_or_lose_other_tools(self):
        with patch.object(self.service.model,'poll',side_effect=OSError('busy')):
            with self.assertLogs(level='ERROR'):self.tick()
            self.assertGreater(self.service.retry_at,0)
        self.service.shutdown();self.tick();self.assertIsNone(self.service.card)

    def test_native_close_dismisses_one_alert_without_hiding_the_next(self):
        self.alarm();self.alarm();self.tick()
        previous=self.service.card.alert['id']
        self.service.card.close()
        self.assertTrue(self.service.card.isVisible())
        self.assertNotEqual(self.service.card.alert['id'],previous)
        self.assertEqual(len(self.service.ringing),1)
        self.service.card.close()
        self.assertFalse(self.service.card.isVisible())
        self.assertFalse(self.service.ringing)

    def test_passive_card_uses_shared_overlay_preparation_without_focus(self):
        self.pet.mac_overlay=SimpleNamespace(prepare=Mock())
        self.alarm();self.tick()
        self.pet.mac_overlay.prepare.assert_called_once_with(self.service.card)
        from PyQt6.QtCore import Qt
        self.assertTrue(self.service.card.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))

    def test_deleting_spoken_alert_stops_audio_and_removes_card(self):
        ident=self.alarm();self.tick()
        self.pet.speech.current_tag='agenda:'+self.service.card.alert['id']
        self.store.agenda.delete(ident)
        self.service.refresh()
        self.assertFalse(self.service.card.isVisible());self.assertFalse(self.service.ringing)
        self.pet.speech.stop.assert_called_once_with(announce=False)

    def test_new_alarm_takes_precedence_over_older_calendar_notice(self):
        self.store.agenda.save_event('Prima il calendario','2032-03-05T07:59:00','2032-03-05T09:00:00',
                                    reminder_minutes=0,now=self.now-120)
        self.tick(self.now-60)
        self.assertEqual(self.service.card.alert['kind'],'event')
        self.alarm();self.tick()
        self.assertEqual(self.service.card.alert['kind'],'alarm')
        self.service.card.dismiss()
        self.assertEqual(self.service.card.alert['kind'],'event')
        self.assertTrue(self.service.card.isVisible())

    def test_missed_update_refreshes_history_without_showing_or_speaking(self):
        self.alarm();signals=[];self.pet.agenda_changed.connect(lambda:signals.append(True))
        self.tick(self.now+3600)
        self.assertIsNone(self.service.card);self.pet.speech.speak.assert_not_called()
        self.pet.effect.play.assert_not_called();self.assertEqual(len(signals),1)
        self.assertEqual(len(self.store.agenda.missed_alerts()),1)

    def test_idle_tick_does_not_query_storage_rebuild_ui_or_prepare_audio(self):
        self.alarm();self.tick(self.now-60)
        statements=[];self.store.db.set_trace_callback(statements.append)
        with patch.object(self.service,'present') as present:
            self.tick(self.now-59);self.tick(self.now-58)
            present.assert_not_called()
        self.store.db.set_trace_callback(None)
        self.assertEqual(statements,[])
        self.pet.sound.prepare.assert_not_called()

    def test_repeated_model_tick_keeps_seen_card_then_new_occurrence_replaces_it(self):
        self.store.agenda.save_alarm('Giornaliera','08:00',weekdays=list(range(7)),now=self.now-120)
        self.tick();first=self.service.card.alert['id']
        self.tick(self.now+3600)
        self.assertTrue(self.service.card.isVisible());self.assertEqual(self.service.card.alert['id'],first)
        self.tick(self.now+86400)
        self.assertNotEqual(self.service.card.alert['id'],first)
        self.assertEqual(len(self.service.ringing),1)

    def test_failed_dismiss_or_snooze_stops_audio_but_keeps_unsaved_alert_retryable(self):
        import sqlite3
        for action,error in [('dismiss',sqlite3.OperationalError('database is locked')),('snooze',OSError('disk unavailable'))]:
            with self.subTest(action=action):
                self.alarm();self.tick();alert=self.service.card.alert['id']
                before=self.pet.effect.play.call_count
                with patch.object(self.service.model,action,side_effect=error):
                    with self.assertLogs(level='ERROR'):getattr(self.service,action)(alert)
                self.assertFalse(self.service.ringing);self.assertTrue(self.service.card.isVisible())
                self.assertIn('Riprova',self.service.card.when.text())
                self.assertEqual(self.service.model.pending_alerts()[0]['id'],alert)
                self.tick();self.assertEqual(self.pet.effect.play.call_count,before)
                self.service.dismiss(alert);self.assertFalse(self.service.card.isVisible())

    def test_snooze_of_concurrently_removed_alert_reconciles_without_error(self):
        ident=self.alarm();self.tick();alert=self.service.card.alert['id']
        self.store.agenda.delete(ident)
        self.service.snooze(alert)
        self.assertFalse(self.service.card.isVisible());self.assertFalse(self.service.ringing)


class ShortcutIntegrationTests(unittest.TestCase):
    def setUp(self):
        from yun_jin_app import Companion
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False);self.pet=Companion(self.store)
        self.pet.timer.stop();self.pet.reminder_timer.stop();self.pet.study_tools.timer.stop()
        self.pet.context.enabled={key:False for key in ('greeting','time','weather')}
    def tearDown(self):
        self.pet.close();self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()
    def fire(self,name):
        self.pet.hotkeys.dispatch(IDENTS[name]);app.processEvents()
    def test_new_actions_are_unassigned_and_open_lazy_pages_repeatedly(self):
        for name in ('calendar_open','event_new','alarms_open','alarm_new','voice_toggle','alarm_stop','alarm_snooze'):
            self.assertEqual(DEFAULTS[name],'')
        self.assertIsNone(self.pet.panel)
        for name,page in [('calendar_open',8),('alarms_open',9),('calendar_open',8)]:
            self.fire(name);self.assertEqual(self.pet.panel.tabs.currentIndex(),page)
        self.assertIsNone(self.pet.panel.weather_view)
    def test_new_item_shortcuts_create_the_right_dialog_and_do_not_reenter(self):
        windows=[]
        def cancel(dialog,owner):windows.append(dialog.windowTitle());dialog.reject();return QDialog.DialogCode.Rejected
        with patch('yun_jin_app.exec_dialog',side_effect=cancel):
            self.fire('event_new');self.fire('alarm_new');self.fire('event_new')
        self.assertEqual(windows,['Nuovo impegno','Nuova sveglia','Nuovo impegno'])
        self.assertIsNone(self.pet.agenda_editor);self.assertFalse(self.store.agenda.events())
    def test_voice_toggle_persists_syncs_panel_and_gives_feedback_when_hidden(self):
        self.fire('voice_toggle');self.assertFalse(self.pet.speech.enabled)
        self.assertEqual(self.pet.bubble.text,'Voce disattivata')
        self.pet.open_panel(tab=3);self.assertFalse(self.pet.panel.voice_enabled.isChecked())
        self.fire('voice_toggle');self.assertTrue(self.pet.speech.enabled)
        self.assertTrue(self.pet.panel.voice_enabled.isChecked())
        self.assertTrue(self.store.preference('tts_master_enabled',False))

    def due_alarm_and_calendar(self):
        now=datetime(2032,3,5,8).timestamp()
        alarm=self.store.agenda.save_alarm('Esercizio','08:00',on_date='2032-03-05',
                                          voice=False,sound=False,snooze_minutes=7,now=now-120)
        self.store.agenda.save_event('Impegno','2032-03-05T08:00:00','2032-03-05T09:00:00',
                                    voice=False,reminder_minutes=0,now=now-120)
        with patch('time.time',return_value=now):
            self.pet.agenda_service.tick()
        self.assertEqual(self.pet.agenda_service.card.alert['item_id'],alarm)
        return now,self.pet.agenda_service.card.alert['id']

    def test_alarm_shortcuts_are_optional_preserve_ids_and_persist_bindings(self):
        self.assertEqual(list(ACTIONS)[-2:],['alarm_stop','alarm_snooze'])
        self.assertEqual(IDENTS['weather_open'],0x5911+18)
        self.assertEqual(IDENTS['voice_toggle'],0x5911+23)
        self.assertIn('alarm_stop',dict(GROUPS)['Agenda'])
        self.assertIn('alarm_snooze',dict(GROUPS)['Agenda'])
        bindings={**self.pet.hotkeys.bindings,'alarm_stop':'Ctrl+Alt+Shift+F8','alarm_snooze':'Ctrl+Alt+Shift+F9'}
        # A fake registry isolates persistence and duplicate validation from
        # the desktop's unrelated shortcuts, which native tests cover elsewhere.
        backend=SimpleNamespace(register=Mock(return_value=True),unregister_all=Mock(),close=Mock())
        with patch.object(self.pet.hotkeys,'backend',backend):
            self.pet.hotkeys.apply(bindings)
            reloaded=Hotkeys(self.pet,backend)
            try:
                self.assertEqual(reloaded.bindings['alarm_stop'],'Ctrl+Alt+Shift+F8')
                self.assertEqual(reloaded.bindings['alarm_snooze'],'Ctrl+Alt+Shift+F9')
                with self.assertRaises(ValueError):reloaded.apply({**bindings,'alarm_snooze':bindings['alarm_stop']})
            finally:reloaded.close()

    def test_alarm_stop_shortcut_dismisses_only_alarm_and_repeated_press_is_inert(self):
        now,alert=self.due_alarm_and_calendar()
        with patch('time.time',return_value=now):self.fire('alarm_stop')
        pending=self.store.agenda.pending_alerts()
        self.assertEqual([row['kind'] for row in pending],['event'])
        self.assertEqual(self.pet.agenda_service.card.alert['kind'],'event')
        self.assertIsNone(self.pet.panel)
        for name in ('alarm_stop','alarm_snooze','alarm_stop'):self.fire(name)
        self.assertEqual(self.store.agenda.pending_alerts(),pending)

    def test_alarm_snooze_shortcut_uses_its_delay_and_never_moves_snoozed_due_again(self):
        now,alert=self.due_alarm_and_calendar()
        with patch('time.time',return_value=now):self.fire('alarm_snooze')
        snoozed=next(row for row in self.store.agenda.pending_alerts() if row['id']==alert)
        self.assertEqual(snoozed['state'],'snoozed');self.assertEqual(snoozed['due_at'],now+7*60)
        with patch('time.time',return_value=now+20):
            self.fire('alarm_snooze');self.fire('alarm_stop')
        self.assertEqual(next(row for row in self.store.agenda.pending_alerts() if row['id']==alert)['due_at'],now+7*60)
        self.assertEqual(self.pet.agenda_service.card.alert['kind'],'event')
        with patch('time.time',return_value=now+7*60):
            self.pet.agenda_service.tick();self.fire('alarm_stop')
        self.assertEqual([row['kind'] for row in self.store.agenda.pending_alerts()],['event'])

    def test_alarm_shortcuts_without_pending_or_during_shutdown_do_not_create_ui(self):
        self.fire('alarm_stop');self.fire('alarm_snooze')
        self.assertIsNone(self.pet.agenda_service.card);self.assertIsNone(self.pet.panel)
        self.assertEqual(self.store.agenda.alarms(),[])
        self.due_alarm_and_calendar()
        before=self.store.agenda.pending_alerts()
        self.pet.hotkeys.dispatch(IDENTS['alarm_stop'])
        self.pet.closing=True;app.processEvents();self.pet.closing=False
        self.assertEqual(self.store.agenda.pending_alerts(),before)
        self.pet.agenda_service.closed=True
        self.fire('alarm_stop');self.fire('alarm_snooze')
        self.assertEqual(self.store.agenda.pending_alerts(),before)

    def test_calendar_and_alarm_voice_do_not_stop_the_metronome(self):
        self.pet.metronome.running=True
        with patch.object(self.pet.metronome,'stop') as stop:
            for category in ('calendar','alarm'):
                self.pet.speech.category=category;self.pet.voice_animation(True,preparing=True)
                self.pet.voice_animation(True);self.pet.voice_animation(False)
            stop.assert_not_called()
        self.pet.metronome.running=False

    def test_voice_toggle_also_silences_study_audio_without_disabling_alarm_sounds(self):
        from yun_jin_study_widgets import CardFace
        face=CardFace(self.pet);face.player=Mock()
        try:
            self.pet.speech.set_enabled(False);face.player.stop.assert_called_once()
            face.play('missing.mp3');face.player.play.assert_not_called()
            self.assertEqual(face.status.text(),'Voce disattivata');self.assertTrue(self.pet.sound.enabled)
            self.pet.speech.set_enabled(True);face.player.play.assert_not_called()
        finally:face.deleteLater()


if __name__=='__main__':unittest.main(verbosity=2)
