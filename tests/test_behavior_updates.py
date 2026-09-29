import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, QSettings
from yun_jin_core import YunJinPet, ANIMATIONS
from yun_jin_app import Sounds, Companion
from yun_jin_data import Store
from yun_jin_updates_ui import Updates, UpdateDialog
app=QApplication.instance() or QApplication([])

class BehaviorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.pet=YunJinPet(QSettings(str(Path(self.tmp.name)/'pet.ini'),QSettings.Format.IniFormat))
  self.pet.timer.stop();self.pet.cancel();self.pet.mode='normal'
 def tearDown(self):
  self.pet.timer.stop();self.pet.call_timer.stop();self.pet.close();self.pet.deleteLater();self.tmp.cleanup()
 def test_follow_survives_stale_decision_from_every_animation(self):
  for animation in ANIMATIONS:
   if animation.startswith('sleep_'):continue
   self.pet.sequence([(animation,2)])
   self.pet.next_decision=time.monotonic()-30
   self.pet.call_later()
   with patch.object(self.pet,'decide') as decide:
    for _ in range(20):self.pet.tick()
   self.assertEqual(self.pet.state,'follow_pending',animation)
   self.assertTrue(self.pet.call_timer.isActive(),animation);decide.assert_not_called()
   with patch.object(self.pet,'cursor_target',return_value=QPointF(self.pet.pos())):
    self.pet.begin_follow();self.pet.move_step(.1,time.monotonic())
   self.assertTrue(self.pet.following);self.assertEqual(self.pet.state,'move')
 def test_follow_unpauses_and_cancels_cleanly(self):
  self.pet.paused=True;self.pet.call_later();self.assertFalse(self.pet.paused)
  self.pet.set_paused(True);self.assertFalse(self.pet.call_timer.isActive())
  self.pet.paused=False;self.pet.begin_follow()
  with patch.object(self.pet,'cursor_target',return_value=None):self.pet.move_step(.1,time.monotonic())
  self.assertTrue(self.pet.following)
 def test_sleep_three_phases_and_manual_exit(self):
  self.assertTrue(self.pet.start_sleep(2))
  self.assertEqual(self.pet.state,'sleep_enter')
  self.pet.animate(30);self.assertEqual(self.pet.state,'sleep_loop')
  self.pet.animate(30);self.assertEqual(self.pet.sleep_cycles,1)
  self.pet.animate(30);self.assertEqual(self.pet.state,'sleep_exit')
  self.pet.animate(30);self.assertEqual(self.pet.state,'idle')
  self.assertGreater(self.pet.next_sleep,time.monotonic()+899)
  self.pet.set_mode('asleep');self.pet.animate(30)
  for _ in range(15):self.pet.animate(30)
  self.assertEqual(self.pet.state,'sleep_loop')
  self.pet.call_later();self.assertEqual(self.pet.state,'sleep_exit')
  self.pet.animate(30);self.assertEqual(self.pet.state,'follow_pending');self.assertEqual(self.pet.mode,'normal')
 def test_sleep_wake_request_during_descent(self):
  self.pet.start_sleep();self.pet.call_later()
  self.assertEqual(self.pet.state,'sleep_enter')
  self.pet.animate(30);self.assertEqual(self.pet.state,'sleep_exit')
  self.pet.animate(30);self.assertTrue(self.pet.call_timer.isActive())
 def test_reminder_rings_during_metronome_but_respects_mute(self):
  reminder,saved=Mock(),Mock()
  sounds=SimpleNamespace(pet=SimpleNamespace(metronome=SimpleNamespace(running=True)),
    enabled=True,quiet_until=0,interactions=True,last_play=0,effects={'reminder':reminder,'saved':saved},volume=.28)
  Sounds.play(sounds,'saved');saved.play.assert_not_called()
  Sounds.play(sounds,'reminder');reminder.play.assert_called_once()
  reminder.reset_mock();sounds.enabled=False;Sounds.play(sounds,'reminder');reminder.play.assert_not_called()
  sounds.enabled=True;sounds.quiet_until=time.time()+600;Sounds.play(sounds,'reminder');reminder.play.assert_not_called()

 def test_sleep_art_proportions_and_seams(self):
  from statistics import median
  def band(pix,lo,hi):
   im=pix.toImage();rows=[]
   for y in range(im.height()):
    xs=[x for x in range(im.width()) if im.pixelColor(x,y).alpha()>80]
    if xs:rows.append((y,xs[-1]-xs[0]+1))
   top=rows[0][0];height=rows[-1][0]-top+1
   return median(w for y,w in rows if top+height*lo<=y<top+height*hi)
  original=self.pet.sheet.frames[0,5];row=ANIMATIONS['sleep_in'][0]
  frame=self.pet.sheet.frames[row,0]
  for lo,hi,tolerance in [(.08,.35,4),(.60,.80,6),(.90,1.,3)]:
   self.assertLessEqual(abs(band(frame,lo,hi)-band(original,lo,hi)),tolerance)
  entry=[self.pet.sheet.frames[row,i].toImage() for i in range(8)]
  wake=[self.pet.sheet.frames[ANIMATIONS['sleep_out'][0],i].toImage() for i in range(8)]
  self.assertEqual(entry,list(reversed(wake)))
  looprow=ANIMATIONS['sleep_loop'][0]
  self.assertEqual(entry[-1],self.pet.sheet.frames[looprow,0].toImage())
  self.assertEqual(entry[-1],self.pet.sheet.frames[looprow,5].toImage())

class UpdateUiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
  self.pet=Companion(self.store);self.pet.timer.stop();self.pet.reminder_timer.stop();self.pet.checkpoint_timer.stop()
  self.manager=self.pet.updates;self.manager.initial.stop();self.manager.timer.stop()
 def tearDown(self):
  self.pet.close();self.pet.deleteLater();self.store.close();self.tmp.cleanup()
 def test_skip_only_one_version_and_manual_check_still_offers(self):
  release=dict(version='1.2.0',notes='## Novità\nTest',url='https://github.com/PianothShaveck/yun-jin-companion/releases/tag/v1.2.0',automatic=True)
  self.manager.release=release;self.manager.skip_version()
  self.assertEqual(self.store.preference('updates_skip_version',''),'1.2.0')
  with patch.object(self.manager,'maybe_offer') as offer,patch.object(self.manager,'show_notes') as notes:
   self.manager.on_checked(release,'',False);offer.assert_not_called()
   self.manager.on_checked(release,'',True);notes.assert_called_once()
   self.manager.on_checked(dict(release,version='1.3.0'),'',False);offer.assert_called_once()
 def test_notes_are_readable_and_setting_persists(self):
  self.manager.release=dict(version='1.2.0',notes='## Novità\n- Correzione importante\n<script>bad()</script>',url='https://github.com/PianothShaveck/yun-jin-companion/releases/tag/v1.2.0',automatic=True)
  dialog=UpdateDialog(self.manager);dialog.refresh()
  self.assertIn('Correzione importante',dialog.notes.toPlainText())
  self.assertTrue(dialog.install.isEnabled());dialog.deleteLater()
  self.manager.set_enabled(False);self.assertFalse(self.manager.timer.isActive())
  self.assertFalse(self.store.preference('updates_enabled',True))

if __name__=='__main__':unittest.main(verbosity=2)
