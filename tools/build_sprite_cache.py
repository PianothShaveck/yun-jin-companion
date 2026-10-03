#!/usr/bin/env python3
"""Bake lossless aligned clips. Pillow is required only for this build tool."""
import io
import json
import argparse
import math
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QPainter, QPixmap, QImage
from yun_jin_core import SpriteSheet, animation_fingerprint


def build(names=None):
    from PIL import Image
    app = QApplication.instance() or QApplication([])
    sheet = SpriteSheet(ROOT/'app/spritesheet-yun-jin-v2.png')
    assets = ROOT/'app/assets'
    output = assets/'normalized'; output.mkdir(exist_ok=True)
    checked=0
    for spec in json.loads((assets/'animations.json').read_text())['animations']:
        if names and spec['name'] not in names: continue
        checked += 1
        source = assets/spec['file']
        frames = sheet.load_clip(source, spec, use_cache=False)
        w, h = frames[0].width(), frames[0].height()
        atlas = QPixmap(w*4, h*math.ceil(len(frames)/4)); atlas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(atlas)
        for i, pix in enumerate(frames): painter.drawPixmap(QPoint(i%4*w, i//4*h), pix)
        painter.end()
        target = output/(spec['name']+'-'+animation_fingerprint(source, spec)+'.webp')
        payload = QByteArray(); buffer = QBuffer(payload)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not atlas.save(buffer, 'PNG'):
            raise RuntimeError('Unable to encode '+str(target))
        buffer.close()
        original=bytes(payload)
        encoded=io.BytesIO()
        # exact=True also preserves RGB underneath fully transparent pixels.
        Image.open(io.BytesIO(original)).save(encoded,'WEBP',lossless=True,quality=100,exact=True,method=6)
        raw=encoded.getvalue()
        if QImage.fromData(raw).isNull():
            raise AssertionError('Encoded image is invalid: '+spec['name'])
        if QImage.fromData(raw)!=QImage.fromData(original):
            raise AssertionError('Lossless encoding changed pixels: '+spec['name'])
        temporary = target.with_suffix('.webp.tmp')
        try:
            with temporary.open('wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        baked = sheet.load_clip(source, spec)
        if any(a.toImage() != b.toImage() for a,b in zip(frames,baked)):
            raise AssertionError('Pixels changed: '+spec['name'])
        # Snapshot before deleting: directory iterators can skip entries when
        # their backing directory changes during traversal.
        for old in list(output.glob(spec['name']+'-*')):
            if old.suffix not in ('.png','.webp'):continue
            if old != target: old.unlink()
    print(f'{checked} animation clips: exact pixel round-trip verified.')

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--names', nargs='+')
    build(parser.parse_args().names)
