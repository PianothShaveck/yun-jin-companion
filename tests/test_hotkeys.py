"""Shortcut validation, collision rollback, persistence and native modifier ABI."""
import ctypes,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtWidgets import QApplication,QWidget
from PyQt6.QtCore import Qt
from yun_jin_data import Store
from yun_jin_hotkeys import *
app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class Backend:
    def __init__(self):self.registered={};self.conflict='Ctrl+Shift+S'
    def register(self,ident,sequence):
        if sequence==self.conflict:return False
        self.registered[ident]=sequence;return True
    def unregister_all(self):self.registered.clear()
    def close(self):self.unregister_all()


class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.calls=[];self.pet=SimpleNamespace(store=self.store,hotkey_status='',closing=False,
            open_panel=lambda **kw:self.calls.append('panel'),new_reminder=lambda:self.calls.append('reminder'),
            read_clipboard=lambda:self.calls.append('read'),stop_speech=lambda:self.calls.append('stop'))
        self.backend=Backend();self.hotkeys=Hotkeys(self.pet,self.backend);self.pet.hotkeys=self.hotkeys
    def tearDown(self):self.hotkeys.close();self.store.close();self.tmp.cleanup()
    def test_conflict_rolls_back_all_previous_bindings(self):
        before=dict(self.backend.registered)
        with self.assertRaises(ValueError):self.hotkeys.apply({**DEFAULTS,'stop':'Ctrl+Shift+S'})
        self.assertEqual(self.backend.registered,before);self.assertEqual(self.hotkeys.bindings,DEFAULTS)
        self.assertEqual(self.store.preference('shortcuts_'+sys.platform,{}),{})
    def test_customize_disable_and_reload(self):
        bindings={**DEFAULTS,'stop':'Ctrl+Shift+K','read':''};self.hotkeys.apply(bindings)
        self.assertNotIn(IDENTS['read'],self.backend.registered)
        reloaded=Hotkeys(self.pet,Backend());self.assertEqual(reloaded.bindings,bindings);reloaded.close()
        self.hotkeys.dispatch(IDENTS['stop']);app.processEvents();self.assertEqual(self.calls,['stop'])
    def test_duplicate_and_non_global_combinations_rejected(self):
        with self.assertRaises(ValueError):self.hotkeys.apply({**DEFAULTS,'stop':DEFAULTS['read']})
        for key in ('S','Shift+S','Ctrl+A, Ctrl+B','Ctrl+F12'):
            with self.assertRaises(ValueError):normalize(key,'win32')
        self.assertEqual(normalize('Ctrl+Shift+K'),'Ctrl+Shift+K')
    def test_mac_qt_ctrl_means_command_meta_means_control(self):
        self.assertEqual(native_modifiers('Ctrl+Alt+S','darwin'),256|2048)
        self.assertEqual(native_modifiers('Meta+Shift+S','darwin'),4096|512)
        self.assertEqual(native_modifiers('Ctrl+Alt+S','win32'),2|1)
        self.assertEqual(ctypes.sizeof(MacBackend.ID),8);self.assertEqual(ctypes.sizeof(MacBackend.Spec),8)
    def test_recording_suspends_native_bindings_then_restores_on_cancel(self):
        parent=QWidget();dialog=ShortcutDialog(self.pet,parent);dialog.show();app.processEvents()
        self.assertTrue(self.hotkeys.recording);self.assertEqual(self.backend.registered,{})
        self.hotkeys.dispatch(IDENTS['stop']);app.processEvents();self.assertEqual(self.calls,[])
        dialog.reject();self.assertFalse(self.hotkeys.recording);self.assertEqual(len(self.backend.registered),5)
        dialog.deleteLater();parent.deleteLater()
    def test_native_mac_callback_only_one_press_until_release(self):
        backend=MacBackend.__new__(MacBackend);backend.registered={123:None};backend.pressed=set();events=[]
        backend.callback=events.append
        # Independent SDK values: CarbonEvents.h, not NSEvent subtypes.
        kind=[5]
        def parameter(event,name,typ,actual,size,actualsize,value):
            obj=ctypes.cast(value,ctypes.POINTER(MacBackend.ID)).contents;obj.signature=MacBackend.SIGNATURE;obj.id=123;return 0
        backend.carbon=SimpleNamespace(GetEventParameter=parameter,GetEventKind=lambda event:kind[0])
        backend.handle(None,None,None);backend.handle(None,None,None);self.assertEqual(events,[123])
        kind[0]=6;backend.handle(None,None,None);kind[0]=5;backend.handle(None,None,None);self.assertEqual(events,[123,123])
        kind[0]=9;self.assertEqual(backend.handle(None,None,None),-9874)

    def test_mac_system_shortcuts_rejected_even_if_registration_would_succeed(self):
        backend=MacBackend.__new__(MacBackend);backend.registered={}
        backend.keycode=Mock(return_value=2)
        backend.system_shortcuts=Mock(return_value={(2,256|2048)})
        backend.carbon=SimpleNamespace(RegisterEventHotKey=Mock(return_value=0),GetApplicationEventTarget=lambda:None)
        with self.assertRaisesRegex(ValueError,'macOS'):backend.register(123,'Ctrl+Alt+D')
        backend.carbon.RegisterEventHotKey.assert_not_called()
        self.assertTrue(backend.register(123,'Ctrl+Alt+Shift+D'))
        self.assertEqual(backend.carbon.RegisterEventHotKey.call_args.args[4],1)
        backend.system_shortcuts.return_value=set()  # Dock shortcut disabled by the user.
        self.assertTrue(backend.register(124,'Ctrl+Alt+D'))

    def test_clear_control_is_separate_and_preserves_other_actions(self):
        parent=QWidget();dialog=ShortcutDialog(self.pet,parent);dialog.show();app.processEvents()
        self.assertFalse(dialog.edits['stop'].isClearButtonEnabled())
        dialog.clear_buttons['stop'].click();app.processEvents()
        self.assertTrue(dialog.edits['stop'].keySequence().isEmpty())
        self.assertFalse(dialog.clear_buttons['stop'].isEnabled())
        self.assertEqual(dialog.edits['panel'].keySequence().toString(),DEFAULTS['panel'])
        dialog.save();self.assertEqual(self.hotkeys.bindings['stop'],'')
        dialog.deleteLater();parent.deleteLater()

    def test_live_conflict_check_does_not_save_or_keep_a_temporary_binding(self):
        parent=QWidget();dialog=ShortcutDialog(self.pet,parent);dialog.show();app.processEvents()
        dialog.edits['stop'].setKeySequence(QKeySequence('Ctrl+Shift+S'));dialog.validate_edits()
        self.assertFalse(dialog.save_button.isEnabled());self.assertIn('in uso',dialog.error.text())
        self.assertFalse(self.backend.registered);self.assertEqual(self.hotkeys.bindings,DEFAULTS)
        self.backend.conflict='';dialog.validate_edits()
        self.assertTrue(dialog.save_button.isEnabled());dialog.save()
        self.assertEqual(self.hotkeys.bindings['stop'],'Ctrl+Shift+S')
        self.assertEqual(self.backend.registered[IDENTS['stop']],'Ctrl+Shift+S')
        dialog.deleteLater();parent.deleteLater()

    def test_optional_actions_preserve_saved_keys_and_detect_cross_tab_duplicates(self):
        self.assertEqual({k for k,v in DEFAULTS.items() if v},set(LEGACY_DEFAULTS))
        self.assertEqual({key for _,keys in GROUPS for key in keys},set(ACTIONS))
        saved={**LEGACY_DEFAULTS,'panel':'Ctrl+Alt+F8'}
        self.store.set_preference('shortcuts_'+sys.platform,saved)
        loaded=Hotkeys(self.pet,Backend())
        self.assertEqual(loaded.bindings['panel'],'Ctrl+Alt+F8');self.assertEqual(loaded.bindings['stopwatch_toggle'],'');loaded.close()
        dialog=ShortcutDialog(self.pet);dialog.show();app.processEvents();dialog.tabs.setCurrentIndex(2)
        dialog.edits['stopwatch_toggle'].setKeySequence(QKeySequence(DEFAULTS['panel']));dialog.validate_edits()
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.edits['stopwatch_toggle'].setKeySequence(QKeySequence('Ctrl+Alt+F9'));dialog.validate_edits();dialog.save()
        self.assertEqual(self.backend.registered[IDENTS['stopwatch_toggle']],'Ctrl+Alt+F9')
        self.assertEqual(self.hotkeys.bindings['panel'],DEFAULTS['panel']);dialog.deleteLater()

    @unittest.skipUnless(sys.platform=='darwin','Requires native macOS Carbon')
    def test_native_mac_registration_and_cleanup(self):
        backend=MacBackend(lambda ident:None)
        try:
            self.assertTrue(backend.register(23456,'Ctrl+Meta+Shift+F19'))
            self.assertIn(23456,backend.registered)
            self.assertIsInstance(backend.keycode(ord('J')),int)
            self.assertIsInstance(backend.system_shortcuts(),set())
            # Dispatch real Carbon events through the installed native handler.
            events=[];backend.callback=events.append;c=backend.carbon;p=ctypes.c_void_p;u=ctypes.c_uint32
            c.CreateEvent.argtypes=[p,u,u,ctypes.c_double,u,ctypes.POINTER(p)];c.CreateEvent.restype=ctypes.c_int32
            c.SetEventParameter.argtypes=[p,u,u,u,p];c.SetEventParameter.restype=ctypes.c_int32
            c.SendEventToEventTarget.argtypes=[p,p];c.SendEventToEventTarget.restype=ctypes.c_int32
            c.ReleaseEvent.argtypes=[p];c.ReleaseEvent.restype=None
            for kind in (5,5,6,5,6):
                event=p();ident=MacBackend.ID(MacBackend.SIGNATURE,23456)
                self.assertEqual(c.CreateEvent(None,0x6b657962,kind,0.,0,ctypes.byref(event)),0)
                try:
                    self.assertEqual(c.SetEventParameter(event,0x2d2d2d2d,0x686b6964,ctypes.sizeof(ident),ctypes.byref(ident)),0)
                    self.assertEqual(c.SendEventToEventTarget(event,c.GetApplicationEventTarget()),0)
                finally:c.ReleaseEvent(event)
            self.assertEqual(events,[23456,23456])
            # A separate application must not be allowed to share this binding.
            script="""import sys
from PyQt6.QtWidgets import QApplication
from yun_jin_hotkeys import MacBackend
app=QApplication([]);backend=MacBackend(lambda _:None)
try:
    registered=backend.register(23457,'Ctrl+Meta+Shift+F19')
    print('occupied' if not registered else 'unexpectedly registered',flush=True)
finally:backend.close()
"""
            child=subprocess.run([sys.executable,'-c',script],env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'app')},capture_output=True,text=True,timeout=10)
            self.assertEqual(child.returncode,0,child.stderr)
            self.assertEqual(child.stdout.strip(),'occupied')
            backend.unregister_all();self.assertFalse(backend.registered)
        finally:backend.close()

    @unittest.skipUnless(sys.platform=='win32','Requires Windows RegisterHotKey')
    def test_native_windows_registration_and_cleanup(self):
        backend=WindowsBackend(lambda ident:None)
        try:
            self.assertTrue(backend.register(23456,'Ctrl+Alt+Shift+F19'))
            backend.unregister_all();self.assertFalse(backend.registered)
        finally:backend.close()


class ActionTests(unittest.TestCase):
    def setUp(self):
        from yun_jin_app import Companion
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False);self.pet=Companion(self.store)
        for timer in (self.pet.timer,self.pet.reminder_timer,self.pet.checkpoint_timer,self.pet.study_tools.timer):timer.stop()
        self.pet.context.enabled={k:False for k in ('greeting','time','weather')}
        self.pet.cancel();self.pet.idle();self.pet.mode='normal';self.pet.paused=False
        self.pet.hotkeys.close();self.pet.hotkeys=Hotkeys(self.pet,Backend())
    def tearDown(self):
        self.pet.close();self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()
    def fire(self,name):
        self.pet.hotkeys.dispatch(IDENTS[name]);app.processEvents()

    def test_stopwatch_repeats_pauses_keeps_laps_and_resets_without_opening_panel(self):
        watch=self.pet.stopwatch
        self.fire('stopwatch_toggle');self.assertTrue(watch.running)
        watch.started-=2;self.fire('stopwatch_lap');self.assertEqual(len(watch.laps),1)
        self.fire('stopwatch_toggle');self.assertFalse(watch.running);elapsed=watch.elapsed()
        self.fire('stopwatch_lap');self.assertEqual(len(watch.laps),1)
        self.fire('stopwatch_toggle');self.assertTrue(watch.running);self.assertGreaterEqual(watch.elapsed(),elapsed)
        self.fire('stopwatch_reset');self.assertFalse(watch.running);self.assertEqual(watch.elapsed(),0);self.assertEqual(watch.laps,[])
        self.assertIsNone(self.pet.panel)

    def test_metronome_and_focus_use_saved_or_current_controls_without_opening_panel(self):
        self.store.set_preference('metronome',{'bpm':96});self.store.set_preference('focus_minutes',17)
        def start(config):self.pet.metronome.running=True;return True
        with patch.object(self.pet.metronome,'start',side_effect=start) as launch:
            self.fire('metronome_toggle');self.assertEqual(launch.call_args.args[0].bpm,96)
            self.assertTrue(self.pet.metronome.running);self.assertIsNone(self.pet.panel)
            self.fire('metronome_toggle');self.assertFalse(self.pet.metronome.running)
            self.fire('metronome_toggle');self.assertEqual(launch.call_count,2);self.fire('metronome_toggle')
            self.fire('focus_toggle');self.assertTrue(self.pet.focus_active());self.assertEqual(self.store.preference('focus_minutes',0),17)
            self.assertIsNone(self.pet.panel);self.fire('focus_toggle');self.assertFalse(self.pet.focus_active())
            self.fire('metronome_open');self.pet.panel.music.bpm.setValue(112);self.pet.panel.hide()
            self.fire('metronome_toggle');self.assertEqual(launch.call_args.args[0].bpm,112)
            self.assertFalse(self.pet.panel.isVisible());self.fire('metronome_toggle')
            self.pet.panel.focus_minutes.setValue(12);self.fire('focus_toggle')
            self.assertEqual(self.store.preference('focus_minutes',0),12);self.fire('focus_toggle')

    def test_metronome_failure_opens_its_controls_instead_of_silently_failing(self):
        with patch.object(self.pet.metronome,'start',side_effect=ImportError('audio unavailable')):
            self.fire('metronome_toggle')
        self.assertFalse(self.pet.metronome.running);self.assertTrue(self.pet.panel.isVisible())
        self.assertIn('Audio non disponibile',self.pet.panel.music.status.text())

    def test_note_and_clipboard_actions_preserve_unsaved_text_and_open_correct_tools(self):
        self.fire('note');self.pet.panel.body.setPlainText('Appunto da conservare')
        self.fire('note');self.assertEqual(self.store.notes()[0]['body'],'Appunto da conservare')
        self.assertEqual(self.pet.panel.body.toPlainText(),'')
        QApplication.clipboard().setText('Testo copiato');self.fire('capture')
        self.assertEqual(self.pet.panel.body.toPlainText(),'Testo copiato')
        self.fire('stopwatch_open');self.assertEqual(self.pet.panel.music.tabs.currentIndex(),1)
        self.fire('focus_open');self.assertEqual(self.pet.panel.tabs.currentIndex(),4)
        self.fire('pet_pause');self.assertTrue(self.pet.paused)
        self.fire('pet_pause');self.assertFalse(self.pet.paused)
        self.fire('quiet');self.assertGreater(self.pet.sound.quiet_until,time.time())
        self.fire('quiet');self.assertEqual(self.pet.sound.quiet_until,0)

    def test_shortcut_feedback_reports_pause_elapsed_laps_and_resuming(self):
        self.pet.show();app.processEvents()
        with patch.object(self.pet,'focus_tool') as focus,patch.object(self.pet.speech,'speak') as speak:
            self.fire('stopwatch_toggle');self.assertEqual(self.pet.bubble.text,'Cronometro avviato')
            self.pet.stopwatch.started-=3
            self.fire('stopwatch_lap');self.assertTrue(self.pet.bubble.text.startswith('Parziale 1 · '))
            self.fire('stopwatch_toggle')
            from yun_jin_music import format_elapsed
            self.assertEqual(self.pet.bubble.text,'Cronometro in pausa · '+format_elapsed(self.pet.stopwatch.elapsed()))
            self.assertTrue(self.pet.bubble.isVisible())
            self.fire('stopwatch_lap');self.assertEqual(len(self.pet.stopwatch.laps),1)
            self.assertIn('Avvia il cronometro',self.pet.bubble.text)
            self.fire('stopwatch_toggle');self.assertEqual(self.pet.bubble.text,'Cronometro ripreso')
            self.fire('stopwatch_reset');self.assertEqual(self.pet.bubble.text,'Cronometro azzerato')
            self.assertTrue(self.pet.shortcut_timer.isSingleShot());self.assertTrue(self.pet.shortcut_timer.isActive())
            focus.assert_not_called();speak.assert_not_called()
        self.assertIsNone(self.pet.panel)

    def test_feedback_for_other_non_window_shortcuts_and_during_focus(self):
        self.pet.show();app.processEvents()
        for action,on,off in [('pet_pause','Yun Jin in pausa','Yun Jin riprende'),
                              ('quiet','Silenzio per un’ora','Silenzio disattivato'),
                              ('focus_toggle','Focus · 25 min','Focus interrotto')]:
            with self.subTest(action=action):
                self.fire(action);self.assertEqual(self.pet.bubble.text,on);self.assertTrue(self.pet.bubble.isVisible())
                self.fire(action);self.assertEqual(self.pet.bubble.text,off)
        def start(config):self.pet.metronome.running=True;return True
        with patch.object(self.pet.metronome,'start',side_effect=start):
            self.fire('metronome_toggle');self.assertEqual(self.pet.bubble.text,'Metronomo avviato')
            self.fire('metronome_toggle');self.assertEqual(self.pet.bubble.text,'Metronomo fermato')
        self.fire('stop');self.assertEqual(self.pet.bubble.text,'Voce interrotta')

    def test_visible_panel_suppresses_feedback_but_minimized_panel_does_not(self):
        self.pet.show();self.fire('stopwatch_toggle');self.assertTrue(self.pet.bubble.isVisible())
        self.fire('stopwatch_open');self.assertFalse(self.pet.bubble.isVisible())
        self.assertFalse(self.pet.shortcut_timer.isActive())
        self.fire('stopwatch_toggle');self.assertFalse(self.pet.bubble.isVisible())
        self.pet.panel.showMinimized();app.processEvents()
        self.fire('stopwatch_toggle');self.assertTrue(self.pet.bubble.isVisible())
        self.assertEqual(self.pet.bubble.text,'Cronometro ripreso')
        self.assertTrue(self.pet.panel.isMinimized())

    def test_queued_shortcut_does_not_execute_after_shutdown_starts(self):
        self.pet.hotkeys.dispatch(IDENTS['stopwatch_toggle']);self.pet.closing=True
        app.processEvents();self.assertFalse(self.pet.stopwatch.running)
        self.assertFalse(self.pet.shortcut_timer.isActive());self.pet.closing=False


if __name__=='__main__':unittest.main(verbosity=2)
