import os,sys,tempfile,time,unittest,importlib.util
from pathlib import Path
from unittest.mock import patch
from fractions import Fraction
import hashlib
os.environ['QT_QPA_PLATFORM']='offscreen'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject
from yun_jin_music import BeatPlan,ClickStream,MetroConfig,Stopwatch,AudioFeed
from yun_jin_data import Store
from yun_jin_app import Companion
from yun_jin_core import ANIMATIONS
app=QApplication([])

class TimingTests(unittest.TestCase):
 def test_constant_no_drift(self):
  p=BeatPlan(MetroConfig(bpm=137),48000)
  for i in range(20000):
   e=p.next();self.assertEqual(e[0],round(Fraction(i*60*48000,137)));self.assertEqual(e[3],i%4==0)
 def test_ramp_beats_and_final_interval(self):
  p=BeatPlan(MetroConfig(bpm=100,ramp=True,target=87,step=6,every=3,finish='stop'),48000)
  es=[p.next() for _ in range(12)]
  self.assertEqual([e[2] for e in es],[100]*3+[94]*3+[88]*3+[87]*3)
  self.assertIsNone(p.next())
 def test_seconds_never_skip_final_tempo(self):
  p=BeatPlan(MetroConfig(bpm=20,accent=0,ramp=True,target=24,step=4,every=1,unit='seconds',finish='stop'),48000)
  self.assertEqual(p.next()[2:],(20,False));self.assertEqual(p.next()[2:],(24,False));self.assertIsNone(p.next())
 def test_pcm_independent_of_chunk_sizes(self):
  c=MetroConfig(bpm=400,accent=3,ramp=True,target=320,step=20,every=4)
  a=ClickStream(c);b=ClickStream(c);counts=[1,11,503,6000,100,12001,319]*15
  one=a.render(sum(counts));pieces=b''.join(b.render(n) for n in counts)
  self.assertEqual(one,pieces);self.assertEqual(list(a.events),list(b.events))
  self.assertNotEqual(a.clicks[True],a.clicks[False]);self.assertTrue(any(one))
 def test_unaligned_audio_reads(self):
  c=MetroConfig();reference=ClickStream(c).render(100)
  feed=AudioFeed(ClickStream(c));sizes=[1,3,27,19,350]
  self.assertEqual(b''.join(feed.readData(n) for n in sizes),reference)
 def test_stopwatch_laps_pause_restart(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store(tmp);w=Stopwatch(s)
   with patch('yun_jin_music.time.monotonic',return_value=100):w.start()
   with patch('yun_jin_music.time.monotonic',return_value=110):w.lap()
   with patch('yun_jin_music.time.monotonic',return_value=123):w.pause()
   self.assertEqual(w.elapsed(),23);self.assertEqual(w.laps[0]['split'],10)
   restored=Stopwatch(s);self.assertFalse(restored.running);self.assertEqual(restored.elapsed(),23)
   with patch('yun_jin_music.time.monotonic',return_value=500):restored.start()
   with patch('yun_jin_music.time.monotonic',return_value=502):self.assertEqual(restored.lap()['split'],15)
   restored.reset();self.assertEqual(restored.elapsed(),0);s.close()

class GuiTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.store=Store(cls.tmp.name);cls.pet=Companion(cls.store)
  cls.pet.timer.stop();cls.pet.reminder_timer.stop();cls.pet.checkpoint_timer.stop()
  cls.pet.open_panel(tab=5);app.processEvents()
 @classmethod
 def tearDownClass(cls):
  cls.pet.close();cls.store.close();cls.tmp.cleanup()
 def test_compact_menu_navigation(self):
  from PyQt6.QtWidgets import QMenu
  self.pet.panel.close()
  menu=QMenu();self.pet.populate_context_menu(menu)
  entries=[a for a in menu.actions() if not a.isSeparator()]
  self.assertEqual(len(entries),9)
  submenus={a.text():a.menu() for a in entries if a.menu()}
  self.assertEqual(set(submenus),{'Strumenti','Voce','Comportamento','Animazioni','Aspetto'})
  music=next(a for a in submenus['Strumenti'].actions() if a.text()=='Metronomo…')
  music.trigger();self.assertEqual(self.pet.panel.tabs.currentIndex(),5)
  self.assertEqual(self.pet.panel.music.tabs.currentIndex(),0)
  chronometer=next(a for a in submenus['Strumenti'].actions() if a.text()=='Cronometro…')
  chronometer.trigger();self.assertEqual(self.pet.panel.music.tabs.currentIndex(),1)
  self.assertTrue(self.pet.panel.nav[(5,1)].isChecked())
  self.pet.panel.nav[(5,0)].click();self.assertEqual(self.pet.panel.music.tabs.currentIndex(),0)
  self.pet.panel.close()
  pause=next(a for a in submenus['Comportamento'].actions() if a.text()=='Pausa completa')
  before=self.pet.paused;pause.trigger();self.assertEqual(self.pet.paused,not before)
  pause.trigger();self.assertEqual(self.pet.paused,before)
  def labels(m):
   result=[]
   for action in m.actions():
    if action.menu():result.extend(labels(action.menu()))
    else:result.append(action.text())
   return result
  for label in ['Nuovo promemoria…','Importa appunti copiati','Riprendi','Riporta sullo schermo']:
   self.assertTrue(any(t.startswith(label) for t in labels(menu)))
  self.pet.populate_context_menu(menu);self.assertEqual(len([a for a in menu.actions() if not a.isSeparator()]),9)
  menu.deleteLater()
 @unittest.skipUnless(sys.platform=='darwin','Requires native macOS AppKit')
 def test_native_dock_icon(self):
  from yun_jin_platform import mac_dock_icon
  self.assertTrue(mac_dock_icon(Path(__file__).resolve().parents[1]/'app/favicon.icns'))
 @unittest.skipUnless(sys.platform=='win32','Requires Windows Shell')
 def test_windows_shortcut_identity(self):
  import os,subprocess
  from yun_jin_windows import stamp_shortcut
  with tempfile.TemporaryDirectory(prefix='yun jin ') as directory:
   link=Path(directory)/'Yun Jin è qui.lnk'
   env=os.environ.copy();env['YUN_TEST_LINK']=str(link);env['YUN_TEST_PYTHON']=sys.executable
   command=('$s=New-Object -ComObject WScript.Shell; '
            '$l=$s.CreateShortcut($env:YUN_TEST_LINK); '
            '$l.TargetPath=$env:YUN_TEST_PYTHON; $l.Save()')
   subprocess.run(['powershell.exe','-NoProfile','-Command',command],env=env,check=True)
   stamp_shortcut(link)  # Includes independent on-disk readback.
   stamp_shortcut(link)  # Updating an existing identity must also work.
 def test_all_animation_frames_are_complete(self):
  from PyQt6.QtGui import QRegion
  from yun_jin_core import ANIMATIONS
  names=['talking16','reminder16','writing16','celebrate16','waiting16','dance16','pirouette16','stretch16','conduct16','stopwatch16']
  reference=self.pet.sheet.frames[0,5]
  for name in names:
   key,count,timing=ANIMATIONS[name]
   self.assertEqual(count,16)
   heights=[]
   for frame in range(count):
    pic=self.pet.sheet.frames[key,frame]
    self.assertEqual(pic.size(),reference.size())
    box=QRegion(pic.mask()).boundingRect();heights.append(box.height())
    self.assertGreaterEqual(box.left(),1,(name,frame))
    self.assertGreaterEqual(box.top(),1,(name,frame))
    self.assertLess(box.right(),pic.width()-1,(name,frame))
    self.assertLess(box.bottom(),pic.height()-1,(name,frame))
   # The new celebration includes a real crouch and tucked legs during a jump.
   # Canvas containment above still checks every pose for accidental clipping.
   if name=='celebrate16':
    self.assertGreater(min(heights),118,name)
    self.assertLess(max(heights)/min(heights),1.55,name)
    self.assertGreater(max(heights)-min(heights),20,name)
    floors=[QRegion(self.pet.sheet.frames[key,i].mask()).boundingRect().bottom() for i in range(count)]
    self.assertGreater(min(floors[0],floors[15])-max(floors[5:8]),8)
   else:
    self.assertGreater(min(heights),140,name)
    self.assertLess(max(heights)/min(heights),1.16,name)
 def test_sequence_preserves_aspect_ratio(self):
  from PyQt6.QtCore import Qt
  from PyQt6.QtGui import QPixmap,QPainter,QColor
  source=QPixmap(512,512);source.fill(Qt.GlobalColor.transparent)
  painter=QPainter(source)
  painter.fillRect(256,210,1,240,QColor('blue'))
  painter.fillRect(236,290,40,40,QColor('red'));painter.end()
  # A square in the artwork must remain a square, even with obsolete metadata.
  spec=dict(sequence_body_height=240,sequence_center=256,sequence_ground=450,
            sequence_horizontal_scale=.87)
  frame=self.pet.sheet.align_sequence([source],spec)[0].toImage()
  points=[(x,y) for y in range(frame.height()) for x in range(frame.width())
          if frame.pixelColor(x,y).alpha()>80 and frame.pixelColor(x,y).red()>200]
  width=max(x for x,y in points)-min(x for x,y in points)+1
  height=max(y for x,y in points)-min(y for x,y in points)+1
  self.assertLessEqual(abs(width-height),1)
 def test_stopwatch_matches_original_head_and_skirt_width(self):
  from statistics import median
  def band_width(pix,low,high):
   im=pix.toImage()
   rows=[]
   for y in range(im.height()):
    xs=[x for x in range(im.width()) if im.pixelColor(x,y).alpha()>80]
    if xs:rows.append((y,xs[-1]-xs[0]+1))
   top=rows[0][0];height=rows[-1][0]-top+1
   return median(w for y,w in rows if top+height*low<=y<top+height*high)
  original=self.pet.sheet.frames[0,5];key=ANIMATIONS['stopwatch16'][0]
  for frame in (0,14,15):
   candidate=self.pet.sheet.frames[key,frame]
   self.assertLessEqual(abs(band_width(candidate,.08,.35)-band_width(original,.08,.35)),4,(frame,'head'))
   self.assertLessEqual(abs(band_width(candidate,.60,.80)-band_width(original,.60,.80)),6,(frame,'skirt'))
 def test_defaults_and_conditional_options(self):
  p=self.pet.panel;p.tabs.setCurrentIndex(3);p.reset_voice();app.processEvents()
  self.assertEqual((p.tts_rate.value(),p.tts_pitch.value(),p.tts_volume.value()),(20,15,70))
  self.assertEqual(p.tts_voice.currentData(),'it-IT-ElsaNeural')
  p.provider.setCurrentIndex(p.provider.findData('google'));app.processEvents()
  self.assertTrue(p.rate_controls.isHidden());self.assertFalse(p.google_slow.isHidden())
  p.reset_voice();self.assertFalse(p.rate_controls.isHidden());self.assertTrue(p.google_slow.isHidden())
 def test_increase_decrease_buttons(self):
  from PyQt6.QtWidgets import QPushButton
  controls=self.pet.panel.rate_controls;spin=self.pet.panel.tts_rate
  buttons=controls.findChildren(QPushButton);old=spin.value();buttons[1].click();self.assertEqual(spin.value(),old+1)
  buttons[0].click();self.assertEqual(spin.value(),old)
 def test_platform_labels(self):
  from yun_jin_platform import shortcut_help,action_label
  with patch('yun_jin_platform.sys.platform','darwin'):
   self.assertNotIn('Ctrl+Alt',shortcut_help());self.assertEqual(action_label('Apri','J'),'Apri')
  with patch('yun_jin_platform.sys.platform','win32'):self.assertIn('Ctrl+Alt+J',action_label('Apri','J'))
 def test_animations_and_restoration(self):
  pet=self.pet;pet.panel.close();pet.paused=True;pet.music_animation(True)
  pet.metronome.running=True;pet.metronome.stream=ClickStream(MetroConfig());pet.metronome.position=18000
  pet.metronome.last_onset=0;pet.metronome.bpm=80;pet.animate(.016)
  self.assertEqual(pet.animation,'conduct16');self.assertEqual(pet.frame,8)
  pet.metronome.running=False;pet.music_animation(False);self.assertTrue(pet.paused)
  self.assertEqual(pet.animation,'idle');pet.paused=False
  pet.queue_feedback('chronometer','review');self.assertEqual(pet.animation,'stopwatch16')
  for name in ('conduct16','stopwatch16'):self.assertEqual(ANIMATIONS[name][1],16)
 def test_original_unchanged(self):
  self.assertEqual(hashlib.sha256((ROOT/'app/spritesheet-yun-jin-v2.png').read_bytes()).hexdigest(),'4e481fafea5149a8198eeb8c6f4e32b1cf8d2fcf359bc86aaf1c1ef8f4d47351')
 def test_dance_and_pirouette_menu_and_performance(self):
  from PyQt6.QtWidgets import QMenu
  pet=self.pet;menu=QMenu();pet.populate_context_menu(menu)
  animations=next(a.menu() for a in menu.actions() if a.text()=='Animazioni')
  once=next(a.menu() for a in animations.actions() if a.text()=='Esegui')
  for label,name in [('Danza','dance16'),('Piroetta','pirouette16')]:
   next(a for a in once.actions() if a.text()==label).trigger()
   self.assertEqual(pet.animation,name)
  self.assertNotEqual(ANIMATIONS['dance16'][0],ANIMATIONS['pirouette16'][0])
  self.assertNotEqual((ROOT/'app/assets/dance-16.png').read_bytes(),(ROOT/'app/assets/pirouette-16.png').read_bytes())
  behavior=next(a.menu() for a in menu.actions() if a.text()=='Comportamento')
  perform=next(a for a in behavior.actions() if a.text()=='Esibizione')
  before=pet.use_extra_animations
  try:
   pet.use_extra_animations=True
   with patch.object(pet,'sequence') as sequence:
    perform.trigger()
    self.assertEqual(sequence.call_args.args[0],[('wave',1),('dance16',1),('pirouette16',1),('wave',1)])
   pet.use_extra_animations=False
   with patch.object(pet,'sequence') as sequence:
    perform.trigger()
    self.assertTrue(all(name in ('review','work','jump','wave') for name,count in sequence.call_args.args[0]))
  finally:pet.use_extra_animations=before;pet.cancel();pet.idle();menu.deleteLater()
 def test_spontaneous_pirouette_respects_behavior(self):
  pet=self.pet;old=(pet.use_extra_animations,pet.mode,pet.previous_action,pet.last_cursor_motion)
  try:
   pet.use_extra_animations=True;pet.mode='normal';pet.previous_action='dance16';pet.last_cursor_motion=100
   with patch.object(pet,'focus_active',return_value=False),patch('yun_jin_app.random.random',return_value=0):
    pet.decide(101)
    self.assertEqual(pet.animation,'pirouette16')
   pet.cancel();pet.idle();pet.mode='quiet'
   with patch.object(pet,'focus_active',return_value=False),patch('yun_jin_app.random.random',return_value=0),patch('yun_jin_core.YunJinPet.decide') as fallback:
    pet.decide(102);fallback.assert_called_once_with(102)
  finally:
   pet.use_extra_animations,pet.mode,pet.previous_action,pet.last_cursor_motion=old
   pet.cancel();pet.idle()
 def test_stop_button_updates_ui(self):
  p=self.pet.panel.music;metro=self.pet.metronome
  metro.running=True;metro.status='In esecuzione';metro.changed.emit();self.assertTrue(p.stop.isEnabled())
  p.stop.click();self.assertFalse(metro.running);self.assertEqual(p.status.text(),'Fermo.');self.assertTrue(p.start.isEnabled())
 def test_missing_audio(self):
  from PyQt6.QtMultimedia import QAudioDevice
  with patch('PyQt6.QtMultimedia.QMediaDevices.defaultAudioOutput',return_value=QAudioDevice()):
   self.assertFalse(self.pet.metronome.start(MetroConfig()))
   self.assertIn('Nessuna uscita',self.pet.metronome.status)

if __name__=='__main__':unittest.main(verbosity=2)
