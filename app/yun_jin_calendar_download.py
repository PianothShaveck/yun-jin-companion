# SPDX-License-Identifier: GPL-3.0-or-later
"""On-demand, verified originals. No network activity until an illustration opens."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import certifi

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest, QSslCertificate, QSslConfiguration

ASSETS = Path(__file__).resolve().parent / 'assets'
CACHE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024


@lru_cache(maxsize=1)
def catalog():
    doc = json.loads((ASSETS / 'calendar-index.json').read_text(encoding='utf-8'))
    if doc.get('protocol') != 1 or not re.fullmatch(r'v\d+\.\d+\.\d+', doc['ref']):
        raise ValueError('Invalid calendar catalog')
    return doc


def original_url(name, ref):
    return f'https://raw.githubusercontent.com/PianothShaveck/yun-jin-companion/{ref}/app/assets/calendar/{name}'


def matches(path, record):
    try:
        return (not path.is_symlink() and path.is_file() and path.stat().st_size == record['bytes']
                and hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256'])
    except OSError:
        return False


def trim_cache(directory, keep, limit=CACHE_BYTES):
    # Only files owned by this cache are candidates for eviction.
    entries = []
    for path in directory.glob('*.webp'):
        if re.fullmatch(r'[0-9a-f]{64}\.webp', path.name) and not path.is_symlink():
            try:
                stat = path.stat()
                entries.append((stat.st_mtime_ns, path, stat.st_size))
            except OSError:
                pass
    total = sum(size for _, _, size in entries)
    for _, path, size in sorted(entries):
        if total <= limit:
            break
        if path != keep:
            try:
                path.unlink()
                total -= size
            except OSError:
                pass


class OriginalLoader(QObject):
    ready = pyqtSignal(object)
    failed = pyqtSignal()

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root)
        self.network = None
        self.reply = None
        self.cancelled = False
        self.payload = bytearray()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timeout)

    def start(self, preview):
        if self.cancelled or self.reply is not None:
            return
        try:
            name = Path(preview).name
            if not re.fullmatch(r'(?:YJ-\d{3}|m\d{2}-[a-z])\.webp', name):
                raise ValueError('Invalid image name')
            doc = catalog()
            self.record = doc['images'][name]
            digest = self.record['sha256']
            if not re.fullmatch(r'[0-9a-f]{64}', digest) or not 0 < self.record['bytes'] <= MAX_IMAGE_BYTES:
                raise ValueError('Invalid image metadata')
            candidates = [Path(preview), ASSETS / 'calendar' / name]
            try:
                local = json.loads((self.root / 'calendar-originals.json').read_text(encoding='utf-8'))
                candidates.append(Path(local['directory']) / name)
            except (OSError, ValueError, KeyError, TypeError):
                pass
            self.cache = self.root / 'calendar-cache'
            self.target = self.cache / (digest + '.webp')
            candidates.append(self.target)
            for path in candidates:
                if matches(path, self.record):
                    if path == self.target:
                        path.touch()
                        trim_cache(self.cache, path)
                    self.ready.emit(path)
                    return
            if self.network is None:
                self.network = QNetworkAccessManager(self)
            request = QNetworkRequest(QUrl(original_url(name, doc['ref'])))
            tls = QSslConfiguration.defaultConfiguration()
            tls.setCaCertificates(QSslCertificate.fromPath(certifi.where()))
            request.setSslConfiguration(tls)
            request.setTransferTimeout(10000)
            request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                                 QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
            request.setRawHeader(b'User-Agent', b'Yun-Jin-Companion-Calendar')
            self.payload.clear()
            self.reply = self.network.get(request)
            self.reply.setReadBufferSize(65536)
            self.reply.readyRead.connect(self.read)
            self.reply.finished.connect(self.finished)
            self.timer.start(25000)
        except (OSError, ValueError, KeyError, TypeError):
            self.failed.emit()

    def read(self):
        if self.reply is None:
            return
        chunk = bytes(self.reply.readAll())
        if len(self.payload) + len(chunk) > self.record['bytes']:
            self.reply.abort()
            return
        self.payload.extend(chunk)

    def finished(self):
        reply = self.reply
        if reply is None:
            return
        self.reply = None
        # Finished may still carry a final chunk. Do not abort recursively here.
        tail = bytes(reply.readAll()) if reply.isOpen() else b''
        if len(self.payload) + len(tail) <= self.record['bytes']:
            self.payload.extend(tail)
        else:
            self.payload.clear()
        self.timer.stop()
        try:
            if self.cancelled:
                return
            if (reply.error() != QNetworkReply.NetworkError.NoError
                    or reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) != 200
                    or len(self.payload) != self.record['bytes']
                    or hashlib.sha256(self.payload).hexdigest() != self.record['sha256']):
                raise ValueError('Invalid download')
            self.cache.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='download-', suffix='.tmp', dir=self.cache)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(self.payload)
                os.replace(temporary, self.target)
            finally:
                Path(temporary).unlink(missing_ok=True)
            trim_cache(self.cache, self.target)
            self.ready.emit(self.target)
        except (OSError, ValueError):
            self.failed.emit()
        finally:
            self.payload.clear()
            reply.deleteLater()

    def timeout(self):
        if self.reply is not None:
            self.reply.abort()

    def cancel(self):
        self.cancelled = True
        self.timer.stop()
        if self.reply is not None:
            self.reply.abort()
