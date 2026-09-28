"""Regression checks for early process identity and actual native window icons."""
import ctypes
import os
from pathlib import Path
import runpy
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
import yun_jin_windows as windows

class IdentityTests(unittest.TestCase):
    def test_launcher_identifies_before_importing_qt_app(self):
        events=[]
        identity=types.ModuleType('yun_jin_windows')
        identity.set_process_identity=lambda:events.append('identity')
        app=types.ModuleType('yun_jin_app')
        app.main=lambda:events.append('main') or 0
        actual_import=__import__
        def importer(name,*args,**kwargs):
            if name=='yun_jin_app':
                self.assertEqual(events,['identity'])
                events.append('import-app')
            return actual_import(name,*args,**kwargs)
        with patch.dict(sys.modules,{'yun_jin_windows':identity,'yun_jin_app':app}), patch('builtins.__import__',side_effect=importer):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(ROOT/'app/yun_jin_pet.py'),run_name='__main__')
        self.assertEqual(result.exception.code,0)
        self.assertEqual(events,['identity','import-app','main'])

    def test_identity_readback_and_com_memory_release(self):
        text=ctypes.create_unicode_buffer(windows.APP_ID)
        shell=types.SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=Mock(return_value=0),
                                    GetCurrentProcessExplicitAppUserModelID=Mock())
        def readback(pointer):
            ctypes.cast(pointer,ctypes.POINTER(ctypes.c_void_p))[0]=ctypes.cast(text,ctypes.c_void_p).value
            return 0
        shell.GetCurrentProcessExplicitAppUserModelID.side_effect=readback
        ole=types.SimpleNamespace(CoTaskMemFree=Mock())
        with patch.object(windows.sys,'platform','win32'), patch.object(windows.C,'windll',types.SimpleNamespace(shell32=shell,ole32=ole),create=True):
            self.assertTrue(windows.set_process_identity())
        shell.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(windows.APP_ID)
        ole.CoTaskMemFree.assert_called_once()

    def test_failed_shell_call_is_not_silently_ignored(self):
        shell=types.SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=Mock(return_value=-2147467259))
        with patch.object(windows.sys,'platform','win32'), patch.object(windows.C,'windll',types.SimpleNamespace(shell32=shell),create=True):
            with self.assertRaisesRegex(OSError,'SetCurrentProcessExplicitAppUserModelID'):
                windows.set_process_identity()

    @unittest.skipUnless(sys.platform=='win32','Requires native Windows GUI and Shell')
    def test_native_process_and_dialog_taskbar_icons(self):
        # Fresh process: Windows HWNDs, not Qt's offscreen fake window IDs.
        code='''
import ctypes,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from yun_jin_windows import set_process_identity, install_taskbar_icons
assert set_process_identity()
from PyQt6.QtWidgets import QApplication,QWidget,QDialog
from PyQt6.QtCore import Qt
app=QApplication([])
controller=install_taskbar_icons(app,Path(sys.argv[1])/'favicon.ico')
user=ctypes.windll.user32
from ctypes import wintypes as W
user.SendMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
user.SendMessageW.restype=W.LPARAM
for window in (QWidget(),QDialog()):
    window.show();app.processEvents()
    for kind,handle in enumerate(controller.handles):
        assert user.SendMessageW(int(window.winId()),0x007F,kind,0)==handle
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
    window.show();app.processEvents()
    for kind,handle in enumerate(controller.handles):
        assert user.SendMessageW(int(window.winId()),0x007F,kind,0)==handle
    window.close()
'''
        env=os.environ.copy();env['QT_QPA_PLATFORM']='windows'
        subprocess.run([sys.executable,'-c',code,str(ROOT/'app')],env=env,check=True,timeout=30)

if __name__=='__main__':
    unittest.main(verbosity=2)
