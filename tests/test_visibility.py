"""Hiding the avatar leaves tools, notifications and recovery paths usable."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_hotkeys import Hotkeys, DEFAULTS, IDENTS, ShortcutDialog
from yun_jin_study import StudyPrompt

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class Backend:
    def __init__(self):self.registered={}
    def register(self,ident,key):self.registered[ident]=key;return True
    def unregister_all(self):self.registered.clear()
    def close(self):self.unregister_all()


class VisibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False)
        self.pet=Companion(self.store)
        self.pet.cancel();self.pet.idle();self.pet.mode='normal';self.pet.paused=False
        self.pet.apply_character_visibility();app.processEvents()
        self.pet.hotkeys.close();self.pet.hotkeys=Hotkeys(self.pet,Backend())
        self.tray=patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=True);self.tray.start()

    def tearDown(self):
        self.pet.close();self.pet.deleteLater();app.processEvents()
        self.tray.stop();self.store.close();self.tmp.cleanup()

    def fire(self,name):
        self.pet.hotkeys.dispatch(IDENTS[name]);app.processEvents()

    def test_optional_shortcut_repeats_and_survives_reload_without_overwriting_old_bindings(self):
        self.assertEqual(DEFAULTS['pet_visibility'],'')
        bindings={**self.pet.hotkeys.bindings,'pet_visibility':'Ctrl+Alt+Shift+H'}
        self.pet.hotkeys.apply(bindings)
        for hidden in (True,False,True,False):
            self.fire('pet_visibility')
            self.assertEqual(self.pet.character_hidden,hidden)
            self.assertEqual(self.pet.isVisible(),not hidden)
            self.assertEqual(self.pet.timer.isActive(),not hidden)
            self.assertEqual(self.store.preference('character_visible',None),not hidden)
            self.assertTrue(self.pet.bubble.isVisible())
        self.pet.hotkeys.close();self.pet.hotkeys=Hotkeys(self.pet,Backend())
        self.assertEqual(self.pet.hotkeys.bindings,bindings)
        self.fire('pet_visibility');self.assertFalse(self.pet.isVisible())

    def test_settings_menu_and_shortcut_agree_and_hidden_startup_does_not_reveal(self):
        self.pet.open_panel(tab=2)
        self.pet.panel.character_visible.setChecked(False)
        self.assertTrue(self.pet.panel.isVisible());self.assertFalse(self.pet.isVisible())
        menu=QMenu();self.pet.populate_context_menu(menu)
        action=next(a for a in menu.actions() if a.text().startswith('Mostra Yun Jin'))
        action.trigger();self.assertTrue(self.pet.isVisible());self.assertTrue(self.pet.panel.character_visible.isChecked())
        self.fire('pet_visibility');self.assertFalse(self.pet.panel.character_visible.isChecked())
        self.assertFalse(self.pet.bubble.isVisible())
        self.pet.close();self.pet.deleteLater();app.processEvents()
        self.pet=Companion(self.store);self.pet.apply_character_visibility()
        self.assertTrue(self.pet.character_hidden);self.assertFalse(self.pet.isVisible());self.assertFalse(self.pet.timer.isActive())
        self.assertTrue(self.pet.reminder_timer.isActive());self.assertTrue(self.pet.study_tools.timer.isActive())
        menu.deleteLater()

    def test_hidden_tools_and_manual_captions_work_without_resuming_animation(self):
        self.pet.set_character_visible(False)
        for name in ('stopwatch_toggle','stopwatch_lap','stopwatch_toggle'):
            self.fire(name)
        self.assertFalse(self.pet.stopwatch.running);self.assertEqual(len(self.pet.stopwatch.laps),1)
        self.assertIn('Cronometro in pausa',self.pet.bubble.text)
        self.assertTrue(self.pet.bubble.detached)
        self.assertTrue(self.pet.current_screen().availableGeometry().contains(self.pet.bubble.geometry()))
        self.pet.clear_shortcut_feedback();self.pet.show_caption('你好')
        self.assertTrue(self.pet.bubble.isVisible());self.assertEqual(self.pet.bubble.text,'你好')
        self.pet.show_caption('')
        self.fire('focus_toggle');self.assertTrue(self.pet.focus_active())
        self.fire('focus_toggle');self.assertFalse(self.pet.focus_active())
        self.pet.metronome.running=True;self.pet.music_animation(True)
        self.assertEqual(self.pet.state,'conducting');self.assertFalse(self.pet.timer.isActive())
        self.pet.set_character_visible(True);self.assertTrue(self.pet.metronome.running)
        self.pet.metronome.running=False;self.pet.music_animation(False)

    def test_hiding_preserves_current_animation_pause_and_deadlines(self):
        self.pet.start_sleep();self.pet.paused=True
        state,animation,frame=self.pet.state,self.pet.animation,self.pet.frame
        before=self.pet.next_decision
        self.pet.set_character_visible(False)
        self.pet.hidden_since-=60
        self.assertEqual((self.pet.state,self.pet.animation,self.pet.frame),(state,animation,frame))
        self.pet.set_character_visible(True)
        self.assertTrue(self.pet.paused);self.assertEqual(self.pet.state,state)
        self.assertGreaterEqual(self.pet.next_decision,before+60)
        self.pet.set_character_visible(False)
        after=Mock();self.pet.wake_up(after,leave_mode=True)
        after.assert_called_once();self.assertFalse(self.pet.is_sleeping())
        self.assertFalse(self.pet.timer.isActive())

    def test_reminders_arrive_and_remain_visible_when_avatar_is_hidden(self):
        rid=self.store.add_reminder('Pausa',time.time()-1)
        with patch.object(self.pet.sound,'play') as sound,patch.object(self.pet.speech,'speak') as speak:
            self.pet.poll_reminders()
            self.assertTrue(self.pet.card.isVisible())
            self.pet.set_character_visible(False)
            self.assertTrue(self.pet.card.isVisible())
            self.pet.card.hide();self.pet.announced.clear();self.pet.poll_reminders()
            self.assertTrue(self.pet.card.isVisible())
            sound.assert_called_with('reminder');speak.assert_called_with('Pausa',category='reminder',tag=rid)
        self.assertIsNone(self.pet.card.parentWidget());self.assertFalse(self.pet.isVisible())
        self.pet.snooze_reminder(rid);self.assertFalse(self.pet.card.isVisible())

    def test_hidden_study_prompt_ignores_frozen_animation_but_respects_focus_and_opens_review(self):
        p=self.pet;t=p.study_tools
        t.anki_enabled=True;t.last_anki=time.time();t.anki_valid_until=time.time()+600
        t.anki_cards=[dict(id=1,note_id=1,front='你好',back='Ciao',front_paths=[],back_paths=[])]
        p.start_sleep();p.mode='asleep';p.paused=True;p.set_character_visible(False)
        self.assertFalse(p.context.can_react());self.assertTrue(t.can_prompt())
        t.next_prompt=0;t.poll()
        self.assertTrue(t.prompt.isVisible());self.assertFalse(p.isVisible())
        self.assertTrue(p.current_screen().availableGeometry().contains(t.prompt.geometry()))
        t.prompt.open();app.processEvents()
        self.assertTrue(t.active_dialog.isVisible());self.assertIsNone(t.active_dialog.parentWidget())
        t.active_dialog.close();app.processEvents()
        p.start_focus(25);t.next_prompt=0;t.poll()
        self.assertFalse(t.prompt.isVisible());self.assertFalse(t.can_prompt())

    def test_without_tray_settings_remain_reachable(self):
        with patch('yun_jin_app.sys.platform','linux'),patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=False):
            self.pet.set_character_visible(False)
            self.assertTrue(self.pet.panel.isVisible())
            self.pet.panel.close();app.processEvents()
            self.assertTrue(self.pet.panel.isMinimized())
            self.pet.open_panel(tab=2);app.processEvents()
            self.assertTrue(self.pet.panel.isVisible());self.assertFalse(self.pet.panel.isMinimized())
            self.pet.panel.character_visible.setChecked(True)
            self.assertTrue(self.pet.isVisible())

    def test_mac_without_tray_never_opens_or_traps_the_panel(self):
        with patch('yun_jin_app.sys.platform','darwin'),patch.object(self.pet,'has_tray_access',return_value=False):
            self.pet.set_character_visible(False)
            self.assertIsNone(self.pet.panel)
            self.pet.open_panel(tab=2)
            self.pet.panel.close();app.processEvents()
            self.assertFalse(self.pet.panel.isVisible())
            self.pet.set_character_visible(True)
            self.assertTrue(self.pet.isVisible())

    def test_windows_preference_is_independent_and_does_not_reveal_manually_hidden_pet(self):
        from yun_jin_windows_overlay import PREFERENCE
        self.pet.set_character_visible(False)
        native=Mock();self.pet.windows_overlay=native
        self.pet.set_windows_overlay(False)
        self.assertFalse(self.store.preference(PREFERENCE,True));native.set_enabled.assert_called_with(False)
        self.pet.set_windows_overlay(True)
        self.assertTrue(self.store.preference(PREFERENCE,False));self.assertFalse(self.pet.isVisible())
        self.pet.windows_overlay=None


if __name__=='__main__':unittest.main(verbosity=2)
