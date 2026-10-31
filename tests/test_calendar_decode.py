"""Exercise slow decoder cancellation and GUI delivery, not just fast images."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
from threading import Event, get_ident
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from PyQt6 import sip
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication
import yun_jin_calendar_decode as d

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class DecodeQueueTests(unittest.TestCase):
    def setUp(self):
        self.queue = d._DecodeQueue(app)
        self.enterContext(patch.object(d, 'decode_queue', return_value=self.queue))
        self.controllers = []
        self.release = Event()
        self.started = Event()
        self.calls = []
        self.worker_threads = []
        self.main_thread = get_ident()
        self.addCleanup(self.cleanup_queue)

    def wait(self, predicate):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and not predicate():
            app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate())

    def cleanup_queue(self):
        for controller in self.controllers:
            if not sip.isdeleted(controller):
                controller.cancel()
                sip.delete(controller)
        self.release.set()
        self.wait(lambda: self.queue.active is None)
        self.queue.shutdown()
        self.queue.deleteLater()
        app.processEvents()

    def controller(self):
        controller = d.OriginalDecoder()
        self.controllers.append(controller)
        return controller

    def slow_read(self, path):
        self.calls.append(path)
        self.worker_threads.append(get_ident())
        if path == 'first':
            self.started.set()
            if not self.release.wait(3):
                raise TimeoutError('Test did not release decoder')
        image = QImage(30 if path == 'first' else 60, 20, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.red)
        return image

    def test_gui_remains_responsive_and_receives_owned_pixels(self):
        decoder = self.controller()
        results = []
        decoder.ready.connect(lambda image: results.append((image, get_ident())))
        with patch.object(d, 'read_image', side_effect=self.slow_read):
            decoder.start('first')
            self.wait(self.started.is_set)
            heartbeat = []
            QTimer.singleShot(0, lambda: heartbeat.append(True))
            self.wait(lambda: heartbeat)
            self.assertFalse(results)
            self.assertNotEqual(self.worker_threads[0], self.main_thread)
            self.release.set()
            self.wait(lambda: results)
        self.assertEqual(results[0][1], self.main_thread)
        self.assertEqual(results[0][0].size().width(), 30)
        self.assertEqual(results[0][0].pixelColor(0, 0), Qt.GlobalColor.red)

    def test_only_one_decode_and_closed_pending_request_is_never_read(self):
        first, closed, last = [self.controller() for _ in range(3)]
        results = []
        last.ready.connect(lambda image: results.append(image.width()))
        with patch.object(d, 'read_image', side_effect=self.slow_read):
            first.start('first')
            self.wait(self.started.is_set)
            closed.start('closed')
            last.start('last')
            self.assertEqual(len(self.queue.pending), 2)
            sip.delete(closed)
            self.assertEqual(len(self.queue.pending), 1)
            self.assertEqual(self.calls, ['first'])
            first.cancel()
            self.release.set()
            self.wait(lambda: results)
        self.assertEqual(self.calls, ['first', 'last'])
        self.assertEqual(results, [60])

    def test_replaced_request_cannot_deliver_stale_pixels(self):
        decoder = self.controller()
        results = []
        decoder.ready.connect(lambda image: results.append(image.width()))
        with patch.object(d, 'read_image', side_effect=self.slow_read):
            decoder.start('first')
            self.wait(self.started.is_set)
            decoder.start('second')
            self.release.set()
            self.wait(lambda: results)
        self.assertEqual(results, [60])

    def test_exception_reports_failure_and_queue_can_be_reused(self):
        decoder = self.controller()
        errors, results = [], []
        decoder.failed.connect(lambda: errors.append(True))
        decoder.ready.connect(lambda image: results.append(image.width()))
        with patch.object(d, 'read_image', side_effect=OSError('unreadable')), self.assertLogs(d.__name__, level='ERROR'):
            decoder.start('bad')
            self.wait(lambda: errors)
        with patch.object(d, 'read_image', side_effect=self.slow_read):
            decoder.start('next')
            self.wait(lambda: results)
        self.assertEqual(results, [60])

    def test_shutdown_drops_pending_and_running_results(self):
        first, pending = self.controller(), self.controller()
        results = []
        first.ready.connect(results.append)
        pending.ready.connect(results.append)
        with patch.object(d, 'read_image', side_effect=self.slow_read):
            first.start('first')
            self.wait(self.started.is_set)
            pending.start('pending')
            self.queue.shutdown()
            self.release.set()
            self.wait(lambda: self.queue.active is None)
        self.assertEqual(self.calls, ['first'])
        self.assertFalse(self.queue.pending)
        self.assertFalse(results)


if __name__ == '__main__':
    unittest.main()
