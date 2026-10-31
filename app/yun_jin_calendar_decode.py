# SPDX-License-Identifier: GPL-3.0-or-later
"""Decode calendar originals off the GUI thread, one image at a time."""
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import partial
import logging
from threading import Event

from PyQt6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage, QImageReader
from PyQt6.QtWidgets import QApplication


def read_image(path):
    """Return owned image pixels; never create a QPixmap in the worker."""
    if str(path).lower().endswith('.jxl'):
        # These libraries are loaded only in the single decode worker, never
        # during startup or when displaying the small WebP calendar preview.
        import pillow_jxl  # Registers the codec with Pillow.
        pillow_jxl.JpegXLImagePlugin.DECODE_THREADS = 2
        from PIL import Image
        with Image.open(path) as source:
            if source.width * source.height > 16_000_000:
                return QImage()
            pixels = source.convert('RGBA')
            raw = pixels.tobytes()
            return QImage(raw, pixels.width, pixels.height, pixels.width*4,
                          QImage.Format.Format_RGBA8888).copy()
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and size.width() * size.height() > 16_000_000:
        reader.setScaledSize(size.scaled(QSize(4096, 4096), Qt.AspectRatioMode.KeepAspectRatio))
    return reader.read()


@dataclass(eq=False)
class _Request:
    path: object
    cancelled: Event = field(default_factory=Event)


class _Task(QRunnable):
    def __init__(self, request, completed):
        super().__init__()
        self.request, self.completed = request, completed

    def run(self):
        image = QImage()
        try:
            if not self.request.cancelled.is_set():
                image = read_image(self.request.path)
        except Exception:
            logging.getLogger(__name__).exception('Calendar image decoding failed')
        if self.request.cancelled.is_set():
            image = QImage()
        try:
            self.completed.emit(self.request, image)
        except RuntimeError:
            # QApplication may already be destroying the queue at shutdown.
            pass


class _DecodeQueue(QObject):
    finished = pyqtSignal(object, QImage)
    _completed = pyqtSignal(object, QImage)

    def __init__(self, parent):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.pool.setExpiryTimeout(1000)
        self.pending = OrderedDict()
        self.active = None
        self.stopping = False
        self._completed.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        parent.aboutToQuit.connect(self.shutdown)

    def submit(self, path):
        request = _Request(path)
        if self.stopping:
            request.cancelled.set()
            return request
        self.pending[request] = None
        self._start_next()
        return request

    def cancel(self, request):
        if request is not None:
            request.cancelled.set()
            self.pending.pop(request, None)

    def _start_next(self):
        if self.active is None and self.pending and not self.stopping:
            self.active, _ = self.pending.popitem(last=False)
            self.pool.start(_Task(self.active, self._completed))

    @pyqtSlot(object, QImage)
    def _finish(self, request, image):
        self.active = None
        try:
            if not request.cancelled.is_set() and not self.stopping:
                self.finished.emit(request, image)
        finally:
            self._start_next()

    def shutdown(self):
        self.stopping = True
        self.cancel(self.active)
        for request in tuple(self.pending):
            self.cancel(request)


def decode_queue():
    """Application-owned queue; closing a dialog never waits for a decoder."""
    app = QApplication.instance()
    queue = getattr(app, '_calendar_decode_queue', None)
    if queue is None:
        queue = app._calendar_decode_queue = _DecodeQueue(app)
    return queue


def _cancel_current(queue, state):
    queue.cancel(state[0])
    state[0] = None


class OriginalDecoder(QObject):
    ready = pyqtSignal(QImage)
    failed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue = decode_queue()
        self._state = [None]
        self.queue.finished.connect(self._finished)
        # This callback owns only the request state, never the dialog/controller.
        self.destroyed.connect(partial(_cancel_current, self.queue, self._state))

    def start(self, path):
        self.cancel()
        self._state[0] = self.queue.submit(path)

    def cancel(self):
        _cancel_current(self.queue, self._state)

    @pyqtSlot(object, QImage)
    def _finished(self, request, image):
        if request is not self._state[0]:
            return
        self._state[0] = None
        if image.isNull():
            self.failed.emit()
        else:
            self.ready.emit(image)
