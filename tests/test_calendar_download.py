"""Exercise actual asynchronous HTTP, verified caching and dialog cancellation."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QImage, QImageReader
from PyQt6.QtWidgets import QApplication
import yun_jin_calendar_download as d
from yun_jin_calendar_ui import CalendarHero, CalendarBackdrop, IllustrationDialog
from yun_jin_data import Store

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class Downloads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests=0;cls.mode='ok';cls.body=b''
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                cls.requests+=1
                if cls.mode=='redirect':
                    self.send_response(302);self.send_header('Location','https://example.invalid/other');self.end_headers();return
                if cls.mode=='error':self.send_error(503);return
                if cls.mode=='slow':time.sleep(.4)
                body=cls.body if cls.mode!='corrupt' else b'X'*len(cls.body)
                if cls.mode=='large':body*=2
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.assets=self.root/'assets';self.assets.mkdir()
        self.preview=self.assets/'calendar-preview/YJ-336.webp';self.preview.parent.mkdir()
        im=QImage(90,60,QImage.Format.Format_RGB32);im.fill(Qt.GlobalColor.blue);im.save(str(self.preview),'WEBP',100)
        full=self.root/'full.webp';im=QImage(300,200,QImage.Format.Format_RGB32);im.fill(Qt.GlobalColor.red);im.save(str(full),'WEBP',100)
        type(self).body=full.read_bytes();type(self).mode='ok';type(self).requests=0
        record=dict(bytes=len(self.body),sha256=hashlib.sha256(self.body).hexdigest(),width=300,height=200)
        self.doc=dict(protocol=1,ref='v1.5.6',images={self.preview.name:record})
        self.enterContext(patch.object(d,'catalog',return_value=self.doc))
        self.enterContext(patch.object(d,'ASSETS',self.assets))
        self.enterContext(patch.object(d,'original_url',return_value=f'http://127.0.0.1:{self.server.server_port}/image'))
        self.loader=d.OriginalLoader(self.root);self.ready=[];self.errors=[]
        self.loader.ready.connect(self.ready.append);self.loader.failed.connect(lambda:self.errors.append(True))
        self.addCleanup(self.cleanup_loader)
    def cleanup_loader(self):
        self.loader.cancel();self.loader.deleteLater();app.processEvents()
    def wait(self,predicate):
        deadline=time.monotonic()+4
        while time.monotonic()<deadline and not predicate():app.processEvents();time.sleep(.005)
        self.assertTrue(predicate())
    def test_download_integrity_cache_hit_and_recovery_from_corrupt_cache(self):
        self.loader.start(self.preview);self.wait(lambda:self.ready or self.errors)
        self.assertFalse(self.errors);self.assertEqual(self.ready[-1].read_bytes(),self.body);self.assertEqual(self.requests,1)
        self.loader.start(self.preview);self.assertEqual(len(self.ready),2);self.assertEqual(self.requests,1)
        self.ready[-1].write_bytes(b'corrupt');self.loader.start(self.preview);self.wait(lambda:len(self.ready)==3)
        self.assertEqual(self.requests,2);self.assertEqual(self.ready[-1].read_bytes(),self.body)
        self.assertFalse(list((self.root/'calendar-cache').glob('*.tmp')))
    def test_source_originals_and_installation_reference_need_no_network(self):
        local=self.assets/'calendar';local.mkdir();(local/self.preview.name).write_bytes(self.body)
        self.loader.start(self.preview);self.assertEqual(self.ready[-1],local/self.preview.name);self.assertEqual(self.requests,0)
        moved=self.root/'checkout';local.rename(moved)
        (self.root/'calendar-originals.json').write_text(json.dumps({'directory':str(moved)}))
        self.loader.start(self.preview);self.assertEqual(self.ready[-1],moved/self.preview.name);self.assertEqual(self.requests,0)
    def test_bad_hash_oversize_redirect_and_http_failure_never_enter_cache(self):
        for mode in ('corrupt','large','redirect','error'):
            type(self).mode=mode;count=len(self.errors)
            self.loader.start(self.preview);self.wait(lambda:len(self.errors)>count)
            self.assertFalse(self.ready);self.assertFalse(list((self.root/'calendar-cache').glob('*.webp')))
        type(self).mode='ok';self.loader.start(self.preview);self.wait(lambda:self.ready)
    def test_timeout_is_retryable(self):
        type(self).mode='slow';self.loader.start(self.preview);self.loader.timer.start(20)
        self.wait(lambda:self.errors);self.assertFalse(self.ready)
        type(self).mode='ok';self.loader.start(self.preview);self.wait(lambda:self.ready)
    def test_cancel_prevents_completion(self):
        type(self).mode='slow';self.loader.start(self.preview);self.loader.cancel()
        for _ in range(20):app.processEvents();time.sleep(.005)
        self.assertFalse(self.ready);self.assertFalse(self.errors);self.assertIsNone(self.loader.reply)
    def test_dialog_preview_error_retry_full_resolution_and_close(self):
        from datetime import date
        from PyQt6.QtWidgets import QWidget
        pet=QWidget();store=Store(self.root);pet.store=store
        dialog=IllustrationDialog(pet,pet,self.preview,date(2026,5,1));type(self).mode='error'
        dialog.show();self.wait(lambda:dialog.retry.isVisible())
        self.assertEqual(dialog.canvas.pixmap.width(),90)
        type(self).mode='ok';dialog.retry.click();self.wait(lambda:dialog.canvas.pixmap.width()==300)
        dialog.close_button.click();self.assertTrue(dialog.canvas.pixmap.isNull());self.assertTrue(dialog.loader.cancelled)
        dialog.deleteLater();pet.deleteLater();store.close();app.processEvents()
    def test_close_before_deferred_load_never_requests_network(self):
        from datetime import date
        from PyQt6.QtWidgets import QWidget
        pet=QWidget();pet.store=Store(self.root)
        dialog=IllustrationDialog(pet,pet,self.preview,date(2026,5,1));dialog.reject();app.processEvents()
        self.assertEqual(self.requests,0);self.assertIsNone(dialog.loader)
        dialog.deleteLater();pet.store.close();pet.deleteLater();app.processEvents()
    def test_lru_eviction_preserves_unknown_files_and_current_image(self):
        cache=self.root/'cache';cache.mkdir()
        paths=[]
        for n in range(3):
            path=cache/(f'{n:064x}.webp');path.write_bytes(b'1234');os.utime(path,(n+1,n+1));paths.append(path)
        unknown=cache/'personal.webp';unknown.write_bytes(b'keep')
        d.trim_cache(cache,paths[-1],limit=8)
        self.assertFalse(paths[0].exists());self.assertTrue(paths[1].exists());self.assertTrue(paths[2].exists())
        self.assertEqual(unknown.read_bytes(),b'keep')


class PreviewPixels(unittest.TestCase):
    def test_every_preview_preserves_the_previous_calendar_pixels(self):
        for original in sorted((ROOT/'app/assets/calendar').glob('*.webp')):
            preview=ROOT/'app/assets/calendar-preview'/original.name
            decoded=[]
            for path in (original,preview):
                reader=QImageReader(str(path));reader.setAutoTransform(True)
                reader.setScaledSize(reader.size().scaled(QSize(1000,600),Qt.AspectRatioMode.KeepAspectRatio))
                decoded.append(reader.read())
            self.assertFalse(decoded[0].isNull(),original.name)
            self.assertEqual(decoded[0],decoded[1],original.name)


if __name__=='__main__':unittest.main()
