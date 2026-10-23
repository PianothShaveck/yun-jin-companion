#!/usr/bin/env python3
"""Store exactly the pixels the calendar already decodes, without lossy encoding."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

from PyQt6.QtCore import QSize, Qt, QBuffer, QIODevice
from PyQt6.QtGui import QImageReader

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app/assets'


def build():
    original_dir = ASSETS / 'calendar'
    preview_dir = ASSETS / 'calendar-preview'
    preview_dir.mkdir(exist_ok=True)
    records = {}
    for source in sorted(original_dir.glob('*.webp')):
        reader = QImageReader(str(source))
        reader.setAutoTransform(True)
        original_size = reader.size()
        reader.setScaledSize(original_size.scaled(QSize(1000, 600), Qt.AspectRatioMode.KeepAspectRatio))
        pixels = reader.read()
        if pixels.isNull():
            raise ValueError(f'Cannot decode {source.name}')
        target = preview_dir / source.name
        existing = QImageReader(str(target))
        if existing.size().isValid():
            existing.setScaledSize(existing.size().scaled(QSize(1000,600),Qt.AspectRatioMode.KeepAspectRatio))
        if existing.read() != pixels:
            # Encode before publishing, so interruption cannot leave an empty file.
            buffer = QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not pixels.save(buffer, 'WEBP', 100):
                raise ValueError(f'Cannot save {source.name}')
            temporary = target.with_suffix('.tmp')
            temporary.write_bytes(bytes(buffer.data()))
            if QImageReader(str(temporary), b'webp').read() != pixels:
                raise ValueError(f'Preview pixels changed: {source.name}')
            temporary.replace(target)
        # Some historical originals use less space than the lossless preview.
        # Keep those original bytes and let the existing reader scale them.
        if source.stat().st_size <= target.stat().st_size:
            shutil.copyfile(source, target)
        records[source.name] = dict(
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            bytes=source.stat().st_size,
            width=original_size.width(), height=original_size.height(),
            preview_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        )
    document = dict(protocol=1, ref='v1.5.6', images=records)
    (ASSETS / 'calendar-index.json').write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    print(f'{len(records)} immagini; originali {sum(p.stat().st_size for p in original_dir.glob("*.webp"))} byte; '
          f'anteprime {sum(p.stat().st_size for p in preview_dir.glob("*.webp"))} byte', flush=True)


if __name__ == '__main__':
    build()
