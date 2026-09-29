#!/usr/bin/env python3
"""Apply the reviewed color calibration to pristine animation sheets.

Developer dependencies: numpy, Pillow. Input hashes prevent double application.
The original sprite sheet, alpha masks, frame positions and timing are untouched.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]

def lab(rgb):
    a = np.asarray(rgb, dtype=float)
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    xyz = lin @ np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.072175], [0.0193339, 0.119192, 0.9503041]]).T
    xyz /= np.array([0.95047, 1, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)

def rgb(lab):
    a = np.asarray(lab, dtype=float)
    fy = (a[..., 0] + 16) / 116
    f = np.stack([fy + a[..., 1] / 500, fy, fy - a[..., 2] / 200], axis=-1)
    xyz = np.where(f > 6 / 29, f ** 3, 3 * (6 / 29) ** 2 * (f - 4 / 29)) * [0.95047, 1, 1.08883]
    lin = xyz @ np.linalg.inv(np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.072175], [0.0193339, 0.119192, 0.9503041]])).T
    return np.clip(np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.maximum(lin, 0) ** (1 / 2.4) - 0.055), 0, 1)

def transfer(a, p):
    L, C, aw, bw, rot, pink, cyan, purple = p
    out = a.copy()
    chroma = np.hypot(a[..., 1], a[..., 2])
    angle = np.arctan2(a[..., 2], a[..., 1])
    hue = np.rad2deg(angle) % 360

    def weight(center):
        dist = (hue - center + 180) % 360 - 180
        return np.exp(-0.5 * (dist / 35) ** 2)
    multiplier = C + pink * weight(10) + cyan * weight(225) + purple * weight(315)
    fade = chroma / (chroma + 12)
    out[..., 0] = np.clip(a[..., 0] + L * np.sin(np.pi * a[..., 0] / 100), 0, 100)
    out[..., 1] = multiplier * chroma * np.cos(angle + rot * np.pi / 180) + aw * fade
    out[..., 2] = multiplier * chroma * np.sin(angle + rot * np.pi / 180) + bw * fade
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-assets',type=Path,required=True,help='Pristine, ungraded assets directory')
    parser.add_argument('--output-assets',type=Path,default=ROOT/'app/assets')
    parser.add_argument('--config',type=Path,default=ROOT/'docs/palette-calibration.json')
    args=parser.parse_args()
    config=json.loads(args.config.read_text())
    sources=[]
    # Check every input before writing any output.
    for name,digest in config['source_assets_sha256'].items():
        path=args.source_assets/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Expected pristine animation sheet: '+str(path))
        sources.append((name,path))
    args.output_assets.mkdir(parents=True,exist_ok=True)
    for name,path in sources:
        pixels=np.array(Image.open(path).convert('RGBA'))
        original_alpha=pixels[:,:,3].copy()
        for start in range(0,len(pixels),128):
            rows=pixels[start:start+128]
            rows[:,:,:3]=np.rint(rgb(transfer(lab(rows[:,:,:3]/255.),config['parameters']))*255).astype(np.uint8)
        assert np.array_equal(pixels[:,:,3],original_alpha)
        stream=io.BytesIO();Image.fromarray(pixels).save(stream,format='PNG',optimize=True)
        (args.output_assets/name).write_bytes(stream.getvalue())
        print(name)

if __name__=='__main__':main()
