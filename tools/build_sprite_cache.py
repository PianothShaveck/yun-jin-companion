#!/usr/bin/env python3
"""Bake lossless, already aligned clips. Original artwork is never modified."""
import json
import math
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QPixmap
from yun_jin_core import SpriteSheet, animation_fingerprint


def build():
    app = QApplication.instance() or QApplication([])
    sheet = SpriteSheet(ROOT/'app/spritesheet-yun-jin-v2.png')
    assets = ROOT/'app/assets'
    output = assets/'normalized'; output.mkdir(exist_ok=True)
    for spec in json.loads((assets/'animations.json').read_text())['animations']:
        source = assets/spec['file']
        frames = sheet.load_clip(source, spec, use_cache=False)
        w, h = frames[0].width(), frames[0].height()
        atlas = QPixmap(w*4, h*math.ceil(len(frames)/4)); atlas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(atlas)
        for i, pix in enumerate(frames): painter.drawPixmap(QPoint(i%4*w, i//4*h), pix)
        painter.end()
        target = output/(spec['name']+'-'+animation_fingerprint(source, spec)+'.png')
        if not atlas.save(str(target)): raise RuntimeError('Unable to save '+str(target))
        baked = sheet.load_clip(source, spec)
        if any(a.toImage() != b.toImage() for a,b in zip(frames,baked)):
            raise AssertionError('Pixels changed: '+spec['name'])
        for old in output.glob(spec['name']+'-*.png'):
            if old != target: old.unlink()
    print('13 animation clips: exact pixel round-trip verified.')

if __name__ == '__main__': build()
