#!/usr/bin/env python3
"""Manual benchmark: process CPU, RSS and paint events; no live network calls.

Usage: python tools/benchmark_performance.py [project-directory]
Use the same interpreter, display backend and machine for both versions.
"""
import os,sys,time,json,tempfile,subprocess
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
root=(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[1]).resolve();sys.path.insert(0,str(root/'app'))
from PyQt6.QtCore import QObject,QEvent,QEventLoop,QTimer,QSettings
from PyQt6.QtWidgets import QApplication
from yun_jin_app import Companion
from yun_jin_data import Store
app=QApplication([]);app.setQuitOnLastWindowClosed(False)
def rss():
 if sys.platform.startswith('linux'):
  return int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')))/1024
 if sys.platform=='darwin':
  return int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())]))/1024
 if sys.platform=='win32':
  import ctypes
  from ctypes import wintypes
  class Counters(ctypes.Structure):
   _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('peak','rss','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
  kernel=ctypes.WinDLL('kernel32');kernel.GetCurrentProcess.restype=wintypes.HANDLE
  counters=Counters();counters.cb=ctypes.sizeof(counters)
  psapi=ctypes.WinDLL('psapi');psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
  if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(),ctypes.byref(counters),counters.cb):raise OSError('Memory query failed')
  return counters.rss/1024**2
 raise RuntimeError('RSS sampling is unavailable on this platform')
class Counter(QObject):
 paints=0
 def eventFilter(self,obj,event):
  if event.type()==QEvent.Type.Paint:self.paints+=1
  return False
with tempfile.TemporaryDirectory() as tmp:
 QSettings.setDefaultFormat(QSettings.Format.IniFormat);QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,tmp)
 store=Store(tmp);store.set_preference('updates_enabled',False)
 t=time.perf_counter();cpu=time.process_time();pet=Companion(store)
 result={'startup_seconds':round(time.perf_counter()-t,3),'startup_cpu_seconds':round(time.process_time()-cpu,3),'rss_start_mib':round(rss(),1)}
 pet.cancel();pet.idle();pet.allow_gaze=False;pet.next_decision=time.monotonic()+3600;pet.next_sleep=time.monotonic()+3600
 counter=Counter();pet.installEventFilter(counter);pet.show();app.processEvents()
 def measure(name):
  pet.next_decision=time.monotonic()+3600;pet.last_cursor_motion=time.monotonic();counter.paints=0
  loop=QEventLoop();QTimer.singleShot(6000,loop.quit);t=time.perf_counter();cpu=time.process_time();loop.exec()
  dt=time.perf_counter()-t
  result[name]={'cpu_ms_per_second':round((time.process_time()-cpu)*1000/dt,2),'paints_per_second':round(counter.paints/dt,2),'rss_mib':round(rss(),1)}
 measure('idle')
 pet.open_panel(tab=5,subtab=1);app.processEvents();pet.panel.hide();pet.stopwatch.start();measure('hidden_stopwatch')
 pet.open_panel(tab=5,subtab=1);app.processEvents();measure('visible_stopwatch')
 frames=pet.sheet.frames
 pixels=list(frames.original.values())+[p for clip in frames.cache.values() for p in clip] if hasattr(frames,'cache') else list(frames.values())
 result['decoded_sprite_mib']=round(sum(p.width()*p.height()*4 for p in pixels)/1024**2,2)
 result['platform']=sys.platform;result['backend']=app.platformName();result['python']=sys.version.split()[0]
 pet.close();store.close();print(json.dumps(result,indent=2))
