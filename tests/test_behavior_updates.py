import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication, QMessageBox, QMenu
from PyQt6.QtCore import QPointF, QSettings, QTimer, Qt
from yun_jin_core import YunJinPet, ANIMATIONS
from yun_jin_app import Sounds, Companion
from yun_jin_data import Store
from yun_jin_updates_ui import Updates, UpdateDialog
app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

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
 def test_spontaneous_walk_and_follow_can_be_enabled_independently(self):
  now=time.monotonic();self.pet.next_sleep=now+1000;self.pet.last_cursor_motion=now
  for walk in (True,False):
   for follow in (True,False):
    with self.subTest(walk=walk,follow=follow):
     self.pet.set_walk(walk);self.pet.set_follow(follow);self.pet.previous_action=None
     with patch('yun_jin_core.random.choices',return_value=['idle']) as choose:self.pet.decide(now)
     choices,weights=choose.call_args.args
     self.assertEqual(weights[choices.index('walk')]>0,walk)
     self.assertEqual(weights[choices.index('follow')]>0,follow)
 def test_motion_toggles_stop_only_their_spontaneous_movement(self):
  now=time.monotonic();self.pet.next_sleep=now+1000;self.pet.last_cursor_motion=now
  for movement in ('walk','follow'):
   self.pet.set_walk(True);self.pet.set_follow(True);self.pet.previous_action=None
   with patch('yun_jin_core.random.choices',return_value=[movement]):self.pet.decide(now)
   self.assertEqual(self.pet.state,'move')
   if movement=='walk':
    self.pet.set_follow(False);self.assertEqual(self.pet.state,'move');self.pet.set_walk(False)
   else:
    self.pet.set_walk(False);self.assertTrue(self.pet.following);self.pet.set_follow(False)
   self.assertEqual(self.pet.state,'idle')
  self.pet.call_later();self.pet.set_follow(False)
  self.assertTrue(self.pet.call_timer.isActive())
  self.pet.begin_follow();self.pet.set_follow(False);self.assertTrue(self.pet.following)
  self.pet.wander();self.pet.set_walk(False);self.assertEqual(self.pet.state,'move')
 def test_legacy_movement_preference_migrates_and_new_choices_persist(self):
  for old_walk in (False,True):
   settings=QSettings(str(Path(self.tmp.name)/f'legacy-{old_walk}.ini'),QSettings.Format.IniFormat)
   settings.setValue('walk',old_walk)
   pet=YunJinPet(settings);pet.timer.stop()
   try:
    self.assertEqual(pet.allow_follow,old_walk)
    pet.set_walk(True);pet.set_follow(False)
   finally:pet.close();pet.deleteLater()
   reloaded=YunJinPet(settings);reloaded.timer.stop()
   try:
    self.assertTrue(reloaded.allow_walk);self.assertFalse(reloaded.allow_follow)
   finally:reloaded.close();reloaded.deleteLater()
 def test_movement_menu_has_independent_checkboxes(self):
  self.pet.set_walk(True);self.pet.set_follow(True)
  menu=QMenu();self.pet.populate_context_menu(menu)
  behavior=next(a.menu() for a in menu.actions() if a.text()=='Comportamento')
  actions={a.text():a for a in behavior.actions()}
  walk=actions['Passeggiate spontanee'];follow=actions['Segui spontaneamente il cursore']
  self.assertTrue(walk.isCheckable());self.assertTrue(follow.isCheckable())
  follow.trigger();self.assertFalse(self.pet.allow_follow);self.assertTrue(self.pet.allow_walk)
  walk.trigger();self.assertFalse(self.pet.allow_walk)
  self.assertFalse(self.pet.settings.value('follow',True,type=bool))
  menu.deleteLater()
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
 def capture_message(self, action, button=QMessageBox.StandardButton.Ok, timeout=5):
  observed={};focused=set();timer=QTimer();deadline=time.monotonic()+timeout
  original_focus=self.pet.focus_tool
  def record_focus(widget):
   original_focus(widget)
   focused.add(widget)
  def inspect_and_close():
   box=app.activeModalWidget()
   try:
    if time.monotonic()>=deadline:
     observed.setdefault('error','Dialog timeout: no focused message box')
    if 'error' in observed:
     if box is not None:box.reject()
     return
    # Wait for the actual focus callback, not a duration measured before Qt
    # has built the message. Font/model initialization can exceed 25 ms on CI.
    if not isinstance(box,QMessageBox) or not box.isVisible() or box not in focused:
     return
    observed.update(box=box,parent=box.parentWidget(),modality=box.windowModality(),
      window_type=box.windowType(),qt_dialog=box.testOption(QMessageBox.Option.DontUseNativeDialog),
      text=box.text(),default=box.standardButton(box.defaultButton()))
    box.button(button).click()
   except Exception as exc:
    observed['error']=str(exc)
    if box is not None and not sip.isdeleted(box):box.reject()
  timer.timeout.connect(inspect_and_close);timer.start(10)
  try:
   with patch.object(self.pet,'focus_tool',side_effect=record_focus):
    result=action()
  finally:timer.stop()
  self.assertNotIn('error',observed);self.assertIn('box',observed)
  self.assertIsNone(app.activeModalWidget())
  return result,observed

 def test_capture_waits_for_slow_focus_callback(self):
  import yun_jin_dialogs as ui
  actual=ui.bring_forward;completed=[]
  def delayed(widget,pet):
   def finish():
    if not sip.isdeleted(widget):
     actual(widget,pet);completed.append(widget)
   QTimer.singleShot(100,finish)
  with patch.object(ui,'bring_forward',side_effect=delayed):
   _,box=self.capture_message(lambda:self.manager.on_checked(None,'',True))
  self.assertIn(box['box'],completed)

 def test_capture_missing_focus_fails_without_hanging(self):
  with patch('yun_jin_dialogs.bring_forward'):
   with self.assertRaisesRegex(AssertionError,'Dialog timeout'):
    self.capture_message(lambda:self.manager.on_checked(None,'',True),timeout=.1)
  self.assertIsNone(app.activeModalWidget())

 def test_manual_results_above_settings_with_mac_overlay_on_and_off(self):
  import yun_jin_dialogs as ui
  from yun_jin_macos import MacOverlay
  levels={};native=Mock()
  native.snapshot.side_effect=lambda widget:(int(widget.winId()),levels.get(widget,0),0)
  native.configure.side_effect=lambda widget,level:levels.__setitem__(widget,level)
  controller=MacOverlay(app,self.pet,native);self.pet.mac_overlay=controller
  try:
   self.pet.open_panel(tab=2)
   for enabled in (True,False):
    self.assertTrue(controller.set_enabled(enabled))
    for error in ('','Connessione non disponibile'):
     with self.subTest(overlay=enabled,error=error),patch.object(ui,'sys',SimpleNamespace(platform='darwin')):
      self.manager.busy=True;self.manager.available_changed.emit()
      _,box=self.capture_message(lambda:self.manager.on_checked(None,error,True))
      self.assertIs(box['parent'],self.pet.panel)
      self.assertEqual(box['modality'],Qt.WindowModality.WindowModal)
      self.assertEqual(box['window_type'],Qt.WindowType.Tool)
      self.assertTrue(box['qt_dialog'])
      self.assertIn(error or 'è aggiornata',box['text'])
      if enabled:
       self.assertGreater(levels[box['box']],levels[self.pet.panel])
       native.focus.assert_any_call(box['box'])
      self.assertTrue(self.pet.panel.update_check.isEnabled())
  finally:
   controller.set_enabled(False);app.removeEventFilter(controller)
   self.pet.mac_overlay=None;controller.deleteLater()

 def test_message_falls_back_to_pet_when_settings_are_closed(self):
  self.pet.open_panel(tab=2);self.pet.panel.hide()
  _,box=self.capture_message(lambda:self.manager.on_checked(None,'',True))
  self.assertIs(box['parent'],self.pet)

 def test_update_confirmation_uses_update_dialog_and_no_cancels(self):
  self.manager.release=dict(version='1.2.0',notes='Correzione',
   url='https://github.com/PianothShaveck/yun-jin-companion/releases/tag/v1.2.0',automatic=True)
  self.manager.show_notes()
  with patch.object(self.manager,'activities_running',return_value=True),patch('yun_jin_update.prepare_update') as prepare:
   _,box=self.capture_message(self.manager.install,QMessageBox.StandardButton.No)
  self.assertIs(box['parent'],self.manager.dialog)
  self.assertEqual(box['default'],QMessageBox.StandardButton.No)
  self.assertFalse(self.manager.installing);prepare.assert_not_called()

 def test_background_check_does_not_open_result_messages(self):
  with patch.object(self.manager,'message') as message:
   self.manager.on_checked(None,'',False)
   self.manager.on_checked(None,'Offline',False)
   message.assert_not_called()

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
