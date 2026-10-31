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
        self.assertEqual(self.loader.source,'download')
        self.loader.start(self.preview);self.assertEqual(len(self.ready),2);self.assertEqual(self.requests,1)
        self.assertEqual(self.loader.source,'cache')
        self.ready[-1].write_bytes(b'corrupt');self.loader.start(self.preview);self.wait(lambda:len(self.ready)==3)
        self.assertEqual(self.requests,2);self.assertEqual(self.ready[-1].read_bytes(),self.body)
        self.assertFalse(list((self.root/'calendar-cache').glob('*.tmp')))
    def test_source_originals_and_installation_reference_need_no_network(self):
        local=self.assets/'calendar';local.mkdir();(local/self.preview.name).write_bytes(self.body)
        self.loader.start(self.preview);self.assertEqual(self.ready[-1],local/self.preview.name);self.assertEqual(self.requests,0)
        self.assertEqual(self.loader.source,'local')
        moved=self.root/'checkout';local.rename(moved)
        (self.root/'calendar-originals.json').write_text(json.dumps({'directory':str(moved)}))
        self.loader.start(self.preview);self.assertEqual(self.ready[-1],moved/self.preview.name);self.assertEqual(self.requests,0)
        self.assertEqual(self.loader.source,'local')
        # Some historical previews already contain the original bytes.
        self.preview.write_bytes(self.body)
        self.loader.start(self.preview);self.assertEqual(self.ready[-1],self.preview);self.assertEqual(self.requests,0)
        self.assertEqual(self.loader.source,'local')
    def test_real_jxl_download_and_decode_retains_full_pixels(self):
        from yun_jin_calendar_decode import read_image
        original=ROOT/'app/assets/calendar/YJ-085.jxl'
        type(self).body=original.read_bytes()
        self.doc['images'][self.preview.name].update(file=original.name,bytes=len(self.body),sha256=hashlib.sha256(self.body).hexdigest())
        self.loader.start(self.preview);self.wait(lambda:self.ready or self.errors)
        self.assertFalse(self.errors);self.assertEqual(self.ready[0].suffix,'.jxl')
        actual=read_image(self.ready[0]);expected=read_image(original)
        self.assertFalse(actual.isNull());self.assertEqual(actual.size(),QSize(1536,1024));self.assertEqual(actual,expected)
        self.loader.start(self.preview);self.assertEqual(self.requests,1)
    def test_original_filename_cannot_escape_catalog_directory(self):
        for name in ('../secret.jxl','/tmp/YJ-001.jxl','YJ-001.jxl?x','YJ-001.exe'):
            self.doc['images'][self.preview.name]['file']=name
            before=len(self.errors);self.loader.start(self.preview)
            self.assertEqual(len(self.errors),before+1);self.assertEqual(self.requests,0)
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
        self.assertEqual(dialog.download_status.text(),'Anteprima')
        dialog.show();self.wait(lambda:dialog.retry.isVisible())
        self.assertEqual(dialog.canvas.pixmap.width(),90)
        self.assertEqual(dialog.download_status.text(),'Anteprima · Originale non disponibile.')
        type(self).mode='ok';dialog.retry.click();self.wait(lambda:dialog.canvas.pixmap.width()==300)
        self.assertEqual(dialog.download_status.text(),'Originale · Scaricato')
        self.assertEqual(dialog.download_status.toolTip(),'300 × 200')
        dialog.close_button.click();self.assertTrue(dialog.canvas.pixmap.isNull());self.assertTrue(dialog.loader.cancelled)
        cached=IllustrationDialog(pet,pet,self.preview,date(2026,5,1));cached.show()
        self.wait(lambda:cached.download_status.text()=='Originale · Cache')
        self.assertEqual(self.requests,2);self.assertFalse(cached.retry.isVisible())
        cached.reject();cached.deleteLater();dialog.deleteLater();pet.deleteLater();store.close();app.processEvents()
    def test_dialog_confirms_registered_local_original_even_offline(self):
        from datetime import date
        from PyQt6.QtWidgets import QWidget
        local=self.root/'checkout';local.mkdir();(local/self.preview.name).write_bytes(self.body)
        (self.root/'calendar-originals.json').write_text(json.dumps({'directory':str(local)}))
        pet=QWidget();pet.store=Store(self.root)
        dialog=IllustrationDialog(pet,pet,self.preview,date(2026,5,1));dialog.show()
        self.wait(lambda:dialog.download_status.text()=='Originale · File locale')
        self.assertEqual(self.requests,0);self.assertEqual(dialog.canvas.pixmap.width(),300)
        dialog.reject();dialog.deleteLater();pet.store.close();pet.deleteLater();app.processEvents()
    def test_matching_hash_but_undecodable_original_keeps_preview_and_error(self):
        from datetime import date
        from PyQt6.QtWidgets import QWidget
        invalid=b'not an image'
        type(self).body=invalid
        self.doc['images'][self.preview.name].update(bytes=len(invalid),sha256=hashlib.sha256(invalid).hexdigest())
        pet=QWidget();pet.store=Store(self.root)
        dialog=IllustrationDialog(pet,pet,self.preview,date(2026,5,1));dialog.show()
        self.wait(lambda:dialog.retry.isVisible())
        self.assertEqual(dialog.canvas.pixmap.width(),90)
        self.assertEqual(dialog.download_status.text(),'Anteprima · Originale non disponibile.')
        self.assertEqual(dialog.download_status.toolTip(),'')
        dialog.reject();dialog.deleteLater();pet.store.close();pet.deleteLater();app.processEvents()
    def test_dialog_loading_status_does_not_claim_original_and_close_cancels(self):
        from datetime import date
        from PyQt6.QtWidgets import QWidget
        type(self).mode='slow';pet=QWidget();pet.store=Store(self.root)
        dialog=IllustrationDialog(pet,pet,self.preview,date(2026,5,1));dialog.show()
        self.wait(lambda:dialog.loader is not None and dialog.loader.reply is not None)
        self.assertEqual(dialog.download_status.text(),'Anteprima · Caricamento originale…')
        self.assertEqual(dialog.canvas.pixmap.width(),90)
        dialog.reject();self.assertTrue(dialog.loader.cancelled);self.assertTrue(dialog.canvas.pixmap.isNull())
        dialog.deleteLater();pet.store.close();pet.deleteLater();app.processEvents()
    def test_direct_catalog_original_is_verified_but_arbitrary_file_is_not_labelled_original(self):
        from datetime import date
        from PyQt6.QtWidgets import QWidget
        local=self.assets/'calendar';local.mkdir();original=local/self.preview.name;original.write_bytes(self.body)
        pet=QWidget();pet.store=Store(self.root)
        dialog=IllustrationDialog(pet,pet,original,date(2026,5,1));dialog.show()
        self.wait(lambda:dialog.download_status.text()=='Originale · File locale')
        self.assertEqual(self.requests,0);dialog.reject();dialog.deleteLater()
        unknown=self.root/'unlisted.webp';unknown.write_bytes(self.body)
        dialog=IllustrationDialog(pet,pet,unknown,date(2026,5,1));dialog.show();app.processEvents()
        self.assertEqual(dialog.download_status.text(),'Immagine locale');self.assertIsNone(dialog.loader)
        self.assertEqual(self.requests,0)
        dialog.reject();dialog.deleteLater();pet.store.close();pet.deleteLater();app.processEvents()
    def test_close_before_deferred_load_never_requests_network(self):
        from datetime import date
        from PyQt6.QtWidgets import QWidget
        pet=QWidget();pet.store=Store(self.root)
        dialog=IllustrationDialog(pet,pet,self.preview,date(2026,5,1));dialog.reject();app.processEvents()
        self.assertEqual(self.requests,0);self.assertIsNone(dialog.loader)
        dialog.deleteLater();pet.store.close();pet.deleteLater();app.processEvents()
    def test_close_during_decode_keeps_gui_live_and_discards_original(self):
        from datetime import date
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QWidget
        import yun_jin_calendar_decode as decode
        local=self.assets/'calendar';local.mkdir();(local/self.preview.name).write_bytes(self.body)
        pet=QWidget();pet.store=Store(self.root)
        dialog=IllustrationDialog(pet,pet,self.preview,date(2026,5,1))
        started=threading.Event();release=threading.Event();read=decode.read_image
        def slow_read(path):
            started.set();release.wait(3)
            return read(path)
        with patch.object(decode,'read_image',side_effect=slow_read):
            try:
                dialog.show();self.wait(started.is_set)
                self.assertEqual(dialog.canvas.pixmap.width(),90)
                self.assertEqual(dialog.download_status.text(),'Anteprima · Caricamento originale…')
                QTimer.singleShot(0,dialog.reject)
                self.wait(lambda:dialog.closed)
                self.assertFalse(release.is_set())
                self.assertTrue(dialog.canvas.pixmap.isNull())
            finally:
                release.set();self.wait(lambda:decode.decode_queue().active is None)
                dialog.reject();dialog.deleteLater();pet.store.close();pet.deleteLater();app.processEvents()
        self.assertTrue(dialog.canvas.pixmap.isNull())
    def test_lru_eviction_preserves_unknown_files_and_current_image(self):
        cache=self.root/'cache';cache.mkdir()
        paths=[]
        for n in range(3):
            path=cache/(f'{n:064x}.'+('jxl' if n==0 else 'webp'));path.write_bytes(b'1234');os.utime(path,(n+1,n+1));paths.append(path)
        unknown=cache/'personal.webp';unknown.write_bytes(b'keep')
        d.trim_cache(cache,paths[-1],limit=8)
        self.assertFalse(paths[0].exists());self.assertTrue(paths[1].exists());self.assertTrue(paths[2].exists())
        self.assertEqual(unknown.read_bytes(),b'keep')


class PreviewPixels(unittest.TestCase):
    def test_previews_match_verified_catalog_and_bounded_historic_conversion(self):
        from PIL import Image, ImageChops
        records=json.loads((ROOT/'app/assets/calendar-index.json').read_text())['images']
        for name,record in records.items():
            preview=ROOT/'app/assets/calendar-preview'/name
            self.assertEqual(hashlib.sha256(preview.read_bytes()).hexdigest(),record['preview_sha256'],name)
            if record['file'].endswith('.webp'):
                with Image.open(ROOT/'app/assets/calendar'/record['file']) as original, Image.open(preview) as reduced:
                    baseline=original.convert('RGB').resize((900,600),Image.Resampling.LANCZOS)
                    self.assertEqual(reduced.size,(900,600),name)
                    self.assertLessEqual(max(high for low,high in ImageChops.difference(baseline,reduced.convert('RGB')).getextrema()),2,name)



if __name__=='__main__':unittest.main()
