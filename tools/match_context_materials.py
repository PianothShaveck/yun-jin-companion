#!/usr/bin/env python3
"""Offline, per-material palette finishing; never changes alpha or geometry.

Fit against the original standing sprite at runtime resolution. A single smooth
color transform per clip is then applied to its pristine atlas, so poses cannot
flicker between independently fitted palettes. No runtime dependency is added.
"""
import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion
from color_match_animations import lab, rgb, transfer

ROOT = Path(__file__).resolve().parents[1]
MATERIALS = {'cyan': (225, 35), 'purple': (310, 27), 'pink': (0, 27), 'red': (35, 18)}
QUANTILES = [.10, .25, .50, .75, .90]


def hue_distance(hue, center):
    return (hue-center+180) % 360-180


def material_mask(values, name):
    center, width = MATERIALS[name]
    chroma = np.hypot(values[..., 1], values[..., 2])
    hue = np.rad2deg(np.arctan2(values[..., 2], values[..., 1])) % 360
    selected = (abs(hue_distance(hue, center)) < width) & (chroma > 12)
    if name == 'pink': selected &= values[..., 0] > 38
    return selected & (values[..., 0] < 90)


def interior(path):
    array = np.asarray(Image.open(path).convert('RGBA'))
    return lab(array[:, :, :3][binary_erosion(array[:, :, 3] > 230)]/255.)


def source_interior(sheet, path, spec):
    from PyQt6.QtGui import QImage
    pic = sheet.load_clip(path, spec, use_cache=False)[0].toImage()
    pic = pic.convertToFormat(QImage.Format.Format_RGBA8888)
    data = pic.constBits(); data.setsize(pic.sizeInBytes())
    rows = np.frombuffer(data, np.uint8).reshape(pic.height(), pic.bytesPerLine())
    array = rows[:, :pic.width()*4].reshape(pic.height(), pic.width(), 4)
    return lab(array[:, :, :3][binary_erosion(array[:, :, 3] > 230)]/255.)


def fit(source, reference):
    result = {}
    for name in MATERIALS:
        src = source[material_mask(source, name)]
        dst = reference[material_mask(reference, name)]
        if min(len(src), len(dst)) < 40: raise ValueError('Too few material samples: '+name)
        sc = np.hypot(src[:, 1], src[:, 2]); dc = np.hypot(dst[:, 1], dst[:, 2])
        sh = np.rad2deg(np.arctan2(src[:, 2], src[:, 1]))
        dh = np.rad2deg(np.arctan2(dst[:, 2], dst[:, 1]))
        center = MATERIALS[name][0]
        turn = np.median(hue_distance(dh, center))-np.median(hue_distance(sh, center))
        source_l = np.quantile(src[:, 0], QUANTILES)
        target_l = np.quantile(dst[:, 0], QUANTILES)
        # Smooth tonal correction, not a palette reduction. Keep highlights,
        # gradients and a bounded shift even for poorly represented shadows.
        result[name] = dict(source_lightness=source_l.tolist(),
            lightness_shift=np.clip(target_l-source_l, -8, 8).tolist(),
            source_chroma=np.quantile(sc, QUANTILES).tolist(),
            chroma_shift=np.clip(np.quantile(dc, QUANTILES)-np.quantile(sc, QUANTILES), -14, 6).tolist(),
            hue_rotation=float(np.clip(turn, -6, 6)),
            reference_median=np.median(dst, axis=0).tolist(),
            source_median=np.median(src, axis=0).tolist())
    return result


def transform(values, corrections, strength=1.):
    hue = np.rad2deg(np.arctan2(values[..., 2], values[..., 1])) % 360
    chroma = np.hypot(values[..., 1], values[..., 2])
    delta = np.zeros_like(values); weight_sum = np.zeros(values.shape[:-1])
    chroma_gate = np.clip((chroma-5)/9, 0, 1)
    light_gate = np.clip((98-values[..., 0])/14, 0, 1)
    for name, correction in corrections.items():
        center, width = MATERIALS[name]
        weight = np.exp(-.5*(hue_distance(hue, center)/(width*.65))**2)
        weight *= chroma_gate*light_gate
        if name == 'pink': weight *= np.clip((values[..., 0]-26)/14, 0, 1)
        target = values.copy()
        target[..., 0] += np.interp(values[..., 0], correction['source_lightness'], correction['lightness_shift'])
        angle = np.deg2rad(hue+correction['hue_rotation'])
        target_chroma = np.maximum(0, chroma+np.interp(chroma, correction['source_chroma'], correction['chroma_shift']))
        target[..., 1] = target_chroma*np.cos(angle)
        target[..., 2] = target_chroma*np.sin(angle)
        delta += (target-values)*weight[..., None]
        weight_sum += weight
    return values+strength*delta/np.maximum(weight_sum, 1)[..., None]


def score(source, reference):
    errors = {}
    for name in MATERIALS:
        a = source[material_mask(source, name)]; b = reference[material_mask(reference, name)]
        errors[name] = float(np.mean(np.linalg.norm(
            np.quantile(a, QUANTILES, axis=0)-np.quantile(b, QUANTILES, axis=0), axis=1)))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--source-assets', type=Path, required=True)
    parser.add_argument('--names', nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--strength', type=float, default=1.)
    parser.add_argument('--base-config', type=Path, help='Apply an existing restrained calibration before material finishing')
    parser.add_argument('--lightness-only', action='store_true', help='Preserve the base palette chroma and hue')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.strength <= 1: parser.error('strength must be between 0 and 1')
    reference = interior(args.review/'frames/original.png')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    sys.path.insert(0, str(ROOT/'app'))
    from PyQt6.QtWidgets import QApplication
    from yun_jin_core import SpriteSheet
    application = QApplication.instance() or QApplication([])
    sheet = SpriteSheet(ROOT/'app/spritesheet-yun-jin-v2.png')
    base = json.loads(args.base_config.read_text())['parameters'] if args.base_config else None
    specs = {s['name']: s for s in json.loads((ROOT/'app/assets/animations.json').read_text())['animations']}
    report = dict(method='Smooth hue-weighted material lightness/chroma/hue correction; no quantization.',
        reference='Original neutral sprite at actual runtime resolution; opaque interiors.',
        metric='Mean distance between CIELAB marginal quantiles within approximate cyan/purple/pink/red hue masks. Screening measure, not perceptual identity.',
        alpha_preserved=True, strength=args.strength, base_parameters=base,
        lightness_only=args.lightness_only, sequences={})
    for name in args.names:
        spec = specs[name]; source = args.source_assets/spec['file']
        # The repeated last frame is excluded from calibration.
        # Decode the supplied pristine atlas directly. An earlier preview may
        # have been rendered with a different grade or normalized cache.
        values = source_interior(sheet, source, spec)
        if base is not None: values = lab(rgb(transfer(values, base)))
        corrections = fit(values, reference)
        if args.lightness_only:
            for correction in corrections.values():
                correction['chroma_shift'] = [0.]*len(QUANTILES)
                correction['hue_rotation'] = 0.
        adjusted = lab(rgb(transform(values, corrections, args.strength)))
        report['sequences'][name] = dict(file=spec['file'], source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            corrections=corrections, before=score(values, reference), after=score(adjusted, reference))
        if args.apply:
            pixels = np.array(Image.open(source).convert('RGBA')); alpha = pixels[:, :, 3].copy()
            for start in range(0, len(pixels), 128):
                rows = pixels[start:start+128]
                colors = lab(rows[:, :, :3]/255.)
                if base is not None: colors = lab(rgb(transfer(colors, base)))
                rows[:, :, :3] = np.rint(rgb(transform(colors, corrections, args.strength))*255).astype(np.uint8)
            assert np.array_equal(alpha, pixels[:, :, 3])
            stream = io.BytesIO(); Image.fromarray(pixels).save(stream, format='PNG', optimize=True)
            (ROOT/'app/assets'/spec['file']).write_bytes(stream.getvalue())
        print(name, report['sequences'][name]['before'], '->', report['sequences'][name]['after'])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__': main()
