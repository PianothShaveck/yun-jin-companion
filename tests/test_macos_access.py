"""Menu-bar recovery without Dock or shortcuts, and actual Cocoa integration."""
import ctypes as C
import importlib.util
import os
from pathlib import Path
import subprocess
import shutil
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
if sys.platform=='darwin':os.environ['QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM']='1'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from PyQt6.QtCore import QEventLoop,QTimer
from PyQt6.QtWidgets import QApplication,QSystemTrayIcon
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_macos import AppKit,MacOverlay,PREFERENCE,FULLSCREEN_AUXILIARY,FULLSCREEN_NONE
from yun_jin_macos_access import MacAccess,NativeStatusItem,Point,Size,Rect,status_icon

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

class FakeStatus:
    def __init__(self,on_open,on_action,on_close):
        self.on_open=on_open;self.on_action=on_action;self.on_close=on_close
        self.available=True;self.closed=False;self.repairs=[];self.policies=[];self.entries=[];self.messages=[]
    def set_accessory(self,value):self.policies.append(value)
    def show(self):pass
    def is_available(self):return self.available
    def create_item(self):self.repairs.append(True)
    def set_menu(self,entries):self.entries=entries
    def show_message(self,*args):self.messages.append(args)
    def close(self):self.closed=True

class AccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False)
        self.pet=Companion(self.store);self.pet.apply_character_visibility()
        self.overlay_native=Mock();self.overlay_native.snapshot.return_value=(123,3,16)
        self.pet.mac_overlay=MacOverlay(app,self.pet,self.overlay_native)
        self.pet.mac_access=MacAccess(app,self.pet,FakeStatus)
        self.access=self.pet.mac_access;self.native=self.access.native
        self.pet.mac_overlay.set_enabled(True);app.processEvents()
    def tearDown(self):
        self.pet.mac_overlay.set_enabled(False);app.removeEventFilter(self.pet.mac_overlay)
        self.pet.mac_overlay.deleteLater();self.pet.close();self.pet.deleteLater();app.processEvents()
        self.store.close();self.tmp.cleanup()
    def choose(self,title):
        self.native.on_open()
        tag=next(k for k,a in self.access.actions.items() if a.text().startswith(title))
        self.native.on_action(tag);self.native.on_close();app.processEvents()
    def test_favicon_keeps_its_colors_and_transparent_background(self):
        icon=status_icon();self.assertFalse(icon.isNull());self.assertFalse(icon.isMask())
        image=icon.pixmap(36,36).toImage()
        pixels=[image.pixelColor(x,y) for y in range(36) for x in range(36)]
        self.assertGreater(max(p.alpha() for p in pixels),200)
        self.assertEqual(min(p.alpha() for p in pixels),0)
        self.assertTrue(any(p.alpha()>200 and p.saturation()>100 for p in pixels))
    def test_qt_fallback_click_keeps_mac_menu_open_without_stealing_focus(self):
        with patch('yun_jin_app.sys.platform','darwin'),patch.object(self.pet,'open_panel') as panel:
            self.pet.tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
            self.pet.tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
            panel.assert_not_called()
        with patch('yun_jin_app.sys.platform','win32'),patch.object(self.pet,'open_panel') as panel:
            self.pet.tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
            panel.assert_called_once_with()
    def test_hide_show_without_shortcuts_never_creates_dock_with_overlay_on_or_off(self):
        self.pet.hotkeys.apply(dict.fromkeys(self.pet.hotkeys.bindings,''))
        for overlay in (True,False,True):
            self.pet.set_mac_overlay(overlay)
            self.pet.set_character_visible(False);app.processEvents()
            self.assertTrue(self.access.is_available());self.assertFalse(self.pet.isVisible())
            self.assertFalse(self.pet.tray.isVisible())  # No duplicate Qt item.
            self.native.on_open();self.assertEqual(self.native.entries[0][1],'Mostra Yun Jin')
            self.native.on_action(self.native.entries[0][0]);self.native.on_close();app.processEvents()
            self.assertTrue(self.pet.isVisible());self.assertEqual(self.store.preference(PREFERENCE,True),overlay)
        self.assertTrue(all(c.args==(True,) for c in self.overlay_native.set_accessory.call_args_list))
        self.assertTrue(all(self.native.policies));self.assertIsNone(self.pet.panel)
    def test_native_menu_preserves_tools_submenus_checks_and_queued_actions(self):
        self.pet.set_character_visible(False)
        self.native.on_open()
        self.assertTrue(self.pet.menu_open)
        self.assertTrue(any(e and e[1]=='Strumenti' and e[4] for e in self.native.entries))
        self.native.on_close();self.assertFalse(self.pet.menu_open)
        self.choose('Pannello…');self.assertTrue(self.pet.panel.isVisible());self.assertFalse(self.pet.isVisible())
        self.choose('Passeggiate spontanee');self.assertFalse(self.pet.allow_walk)
        self.choose('Passeggiate spontanee');self.assertTrue(self.pet.allow_walk)
        self.choose('Studio…');self.assertEqual(self.pet.panel.tabs.currentIndex(),6)
    def test_missing_icon_repair_never_opens_or_traps_the_panel(self):
        self.native.available=False
        self.pet.set_character_visible(False);app.processEvents()
        self.assertEqual(self.native.repairs,[])
        self.assertTrue(self.access.retry_timer.isActive())
        self.access.retry_timer.stop();self.access.verify_repair()
        self.assertEqual(self.native.repairs,[True])
        self.access.retry_timer.stop()
        with patch('yun_jin_macos_access.logging.warning'):
            self.access.verify_repair()
        self.assertIsNone(self.pet.panel)
        self.pet.open_panel(tab=2)
        with patch('yun_jin_panel.sys.platform','darwin'):
            self.pet.panel.close();app.processEvents()
        self.assertFalse(self.pet.panel.isVisible());self.assertFalse(self.pet.panel.isMinimized())
        self.access.verify_repair();app.processEvents()
        self.assertEqual(self.native.repairs,[True])
        self.assertFalse(self.pet.panel.isVisible())
        self.assertFalse(self.access.refresh_timer.isActive());self.assertFalse(self.access.retry_timer.isActive())
        self.assertTrue(all(self.native.policies))
    def test_regular_refresh_keeps_the_same_menu_bar_item(self):
        for _ in range(4):self.access.visibility_changed();app.processEvents()
        self.assertEqual(self.native.repairs,[])
    def test_repeated_accessory_request_does_not_block_tray_repair_or_fullscreen(self):
        bridge=object.__new__(AppKit);bridge.application=123
        bridge.send=Mock(side_effect=lambda _receiver,selector,*args:
            1 if selector=='activationPolicy' else False)
        self.native.set_accessory=bridge.set_accessory
        self.overlay_native.set_accessory.side_effect=bridge.set_accessory
        self.native.available=False
        with patch('yun_jin_macos_access.logging.exception') as errors:
            self.pet.set_character_visible(False);app.processEvents()
            self.assertEqual(self.native.repairs,[])
            self.access.retry_timer.stop();self.access.verify_repair()
            self.assertEqual(self.native.repairs,[True])
            errors.assert_not_called()
        self.native.available=True;self.access.retry_timer.stop()
        for enabled in (False,True,False,True):
            self.assertTrue(self.pet.set_mac_overlay(enabled))
            self.assertEqual(self.pet.mac_overlay.enabled,enabled)
        self.assertIsNone(self.pet.panel)
    def test_zero_height_during_initial_layout_is_not_recreated(self):
        self.native.available=False
        self.access.visibility_changed();app.processEvents()
        self.assertEqual(self.native.repairs,[])
        self.assertTrue(self.access.retry_timer.isActive())
        for _ in range(3):self.access.visibility_changed();app.processEvents()
        self.assertEqual(self.native.repairs,[])
        # The real Mac reports a zero-height frame at loop start, then a
        # visible item after layout. A pending check must keep that item.
        self.native.available=True
        self.access.retry_timer.stop();self.access.verify_repair()
        self.assertEqual(self.native.repairs,[])
        self.assertTrue(self.access.is_available());self.assertIsNone(self.pet.panel)
    def test_notification_click_opens_reminders_while_avatar_stays_hidden(self):
        self.pet.set_character_visible(False)
        self.native.on_action(-1);app.processEvents()
        self.assertEqual(self.pet.panel.tabs.currentIndex(),1);self.assertFalse(self.pet.isVisible())
    def test_shutdown_cancels_queued_action_and_releases_status_item(self):
        self.pet.set_character_visible(False);self.native.on_open()
        self.native.on_action(self.native.entries[0][0]);self.access.close();app.processEvents()
        self.assertFalse(self.pet.isVisible());self.assertTrue(self.native.closed)
        self.assertFalse(self.access.refresh_timer.isActive());self.assertFalse(self.access.action_timer.isActive())
        self.assertFalse(self.pet.menu_open)

class NativeRulesTests(unittest.TestCase):
    def test_status_item_retains_favicon_menu_and_fixed_hit_area(self):
        bridge=object.__new__(NativeStatusItem);bridge.item=None;bridge.bar=1;bridge.menu=2;bridge.image=5
        bridge.string=lambda s:s;calls=[]
        def send(receiver,selector,result=None,types=(),args=()):
            calls.append((receiver,selector,args))
            return {'statusItemWithLength:':3,'button':4}.get(selector)
        bridge.send=send;bridge.create_item()
        self.assertIn((1,'statusItemWithLength:',(32.0,)),calls)
        self.assertIn((3,'retain',()),calls)
        self.assertIn((4,'setImage:',(5,)),calls)
        self.assertIn((3,'setMenu:',(2,)),calls)
        self.assertIn((3,'setVisible:',(True,)),calls)
        self.assertFalse(any(selector in ('setTitle:','setAutosaveName:','setDouble:forKey:')
                             for _,selector,_ in calls))
        bridge.remove_item()
        self.assertIn((1,'removeStatusItem:',(3,)),calls)
        self.assertIn((3,'release',()),calls);self.assertIsNone(bridge.item)
    def test_nonempty_frame_behind_notch_does_not_count_as_accessible(self):
        bridge=object.__new__(NativeStatusItem);bridge.item=1
        bridge.send=lambda receiver,selector,*args,**kwargs:{'isVisible':True,'button':2,'window':3,'screen':4}.get(selector)
        for x,width,expected in ((950,24,False),(1100,24,True),(1100,0,False)):
            bridge.rect=lambda obj,selector:Rect(Point(x,956),Size(width,26)) if obj==3 else Rect(Point(1040,956),Size(472,26))
            self.assertEqual(bridge.is_available(),expected)

class CocoaTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='darwin','Requires native macOS Cocoa')
    def test_bundle_launch_menu_bar_actions_and_no_dock_in_every_visibility_mode(self):
        # Directly launching Python missed the LaunchServices-only tray failure.
        spec=importlib.util.spec_from_file_location('mac_installer',ROOT/'installer/install.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory(prefix="Yun Jin Cocoa ' ") as directory:
            root=Path(directory);program=root/'program';(program/'app').mkdir(parents=True)
            shutil.copyfile(ROOT/'app/favicon.icns',program/'app/favicon.icns')
            bundle=root/'Yun Jin Test.app';done=root/'result';pid=root/'pid'
            (program/'app/yun_jin_pet.py').write_text(
                'import os,runpy,sys,traceback\nfrom pathlib import Path\n'
                f'root=Path({str(root)!r})\n(root/"pid").write_text(str(os.getpid()))\n'
                'os.environ["QT_QPA_PLATFORM"]="cocoa"\n'
                f'sys.argv=[{str(Path(__file__).resolve())!r},"--native"]\n'
                'try:\n runpy.run_path(sys.argv[0],run_name="__main__")\n'
                'except BaseException:\n result=traceback.format_exc()\n'
                'else:\n result="PASS"\n'
                '(root/"result.tmp").write_text(result)\n(root/"result.tmp").replace(root/"result")\n',encoding='utf-8')
            with patch.object(installer,'MAC_BUNDLE_ID','pianoth.yunjin.desktoppet.tests'):
                installer.write_mac_bundle(bundle,Path(sys.executable),program,root)
            try:
                subprocess.run(['/usr/bin/open','-n','-W',str(bundle)],check=True,timeout=10)
                end=time.monotonic()+30
                while not done.exists() and time.monotonic()<end:time.sleep(.05)
                log=root/'launcher.log'
                self.assertTrue(done.exists(),log.read_text(errors='replace') if log.exists() else 'Bundle did not start Python')
                self.assertEqual(done.read_text(),'PASS')
            finally:
                if not done.exists() and pid.exists():
                    try:os.kill(int(pid.read_text()),signal.SIGTERM)
                    except ProcessLookupError:pass

def native_probe():
    def wait_for(condition):
        end=time.monotonic()+5
        while not condition() and time.monotonic()<end:
            loop=QEventLoop();QTimer.singleShot(30,loop.quit);loop.exec()
        assert condition(),'Native Cocoa state did not settle'
    with tempfile.TemporaryDirectory() as directory:
        store=Store(directory);store.set_preference('updates_enabled',False);store.set_preference('character_visible',False)
        pet=Companion(store);pet.hotkeys.close();pet.mac_overlay=MacOverlay(app,pet)
        pet.mac_access=MacAccess(app,pet);native=pet.mac_access.native
        try:
            pet.apply_character_visibility();wait_for(pet.mac_access.is_available)
            button=native.send(native.item,'button')
            assert native.send(button,'image')==native.image
            assert not native.send(native.image,'isTemplate',C.c_bool)
            assert native.send(native.send(button,'title'),'UTF8String',C.c_char_p) in (None,b'')
            assert native.send(native.item,'length',C.c_double)==32.0
            # Repeated requests used to disable the overlay and abort repair
            # even after the native tray had already selected Accessory.
            for _ in range(3):native.set_accessory(True)
            assert pet.mac_overlay.set_enabled(store.preference(PREFERENCE,True))
            for overlay in (True,False,True):
                assert pet.set_mac_overlay(overlay)
                pet.set_character_visible(True);app.processEvents()
                behavior=native.send(native.window(pet),'collectionBehavior',C.c_ulong)
                assert bool(behavior & FULLSCREEN_AUXILIARY)==overlay
                assert bool(behavior & FULLSCREEN_NONE)!=overlay
                pet.set_character_visible(False);wait_for(pet.mac_access.is_available)
                assert not pet.isVisible() and not pet.tray.isVisible()
                assert native.send(native.application,'activationPolicy',C.c_long)==1,'Dock must stay absent'
                native.send(native.target,'menuWillOpen:',None,(C.c_void_p,),(native.menu,))
                item=native.send(native.menu,'itemAtIndex:',types=(C.c_long,),args=(0,))
                title=native.send(native.send(item,'title'),'UTF8String',C.c_char_p).decode()
                assert title=='Mostra Yun Jin',title
                native.send(native.menu,'performActionForItemAtIndex:',None,(C.c_long,),(0,))
                native.send(native.target,'menuDidClose:',None,(C.c_void_p,),(native.menu,))
                wait_for(pet.isVisible)
                assert native.send(native.application,'activationPolicy',C.c_long)==1
            native.create_item();wait_for(pet.mac_access.is_available)
            print('PASS native status item, favicon, menu callbacks, hidden startup, overlay toggles; no Dock')
        finally:
            pet.mac_overlay.set_enabled(False);pet.close();store.close()
            assert native.item is None and native.target is None and native.image is None

if __name__=='__main__':
    if sys.argv[1:]==['--native']:native_probe()
    else:unittest.main(verbosity=2)
