#!/usr/bin/env python3
"""Read-only cwebp near-lossless experiment for calendar previews, never originals.

Output candidates stay in a separate experiment directory. RGB errors and PSNR
are descriptive, not an automatic visual approval or an energy measurement.
"""
import argparse
import hashlib
import json
import math
import platform
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image
from PyQt6.QtCore import qVersion
from benchmark_calendar_codecs import qt_decode, rgba, measure, webp_encoding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--cwebp', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--levels', nargs='+', type=int, default=[100, 90, 80, 60])
    parser.add_argument('--repeat', type=int, default=11)
    args = parser.parse_args()
    if args.repeat < 1 or any(n < 0 or n > 100 for n in args.levels):
        parser.error('repeat must be positive; near-lossless levels must be 0..100')
    if any(p.parent.name != 'calendar-preview' for p in args.files):
        parser.error('only calendar-preview inputs are permitted')
    if len({p.stem for p in args.files}) != len(args.files):
        parser.error('input basenames must be unique')
    output = args.output_dir.resolve()
    if any(p.resolve().is_relative_to(output) or output.is_relative_to(p.parent.resolve()) for p in args.files):
        parser.error('output must be separate from input directories')
    output.mkdir(parents=True, exist_ok=True)
    version = subprocess.check_output([str(args.cwebp.resolve()), '-version'], text=True).strip()
    result = dict(cwebp=version, qt=qVersion(), platform=platform.platform(), repetitions=args.repeat,
                  settings=['-z', '9', '-near_lossless', 'LEVEL', '-exact only for level 100'],
                  limitations=['warm in-memory Qt decoding, not startup or download',
                               'RGB error metrics do not establish perceptual invisibility',
                               'selected previews only; originals and animations excluded'], records=[])
    for source in args.files:
        data = source.read_bytes()
        encoding = webp_encoding(data)
        pixels = rgba(qt_decode(data))
        if any(level < 100 for level in args.levels) and not np.all(pixels[:, :, 3] == 255):
            raise ValueError('Near-lossless experiment currently accepts opaque previews only')
        source_png = output / (source.stem + '-reference.png')
        Image.fromarray(pixels).save(source_png)
        baseline = measure(lambda: qt_decode(data), args.repeat)
        for level in args.levels:
            target = output / f'{source.stem}-near-{level}.webp'
            # In libwebp 1.6, exact also bypasses near-lossless residual
            # quantization. Use it only for the strictly lossless control.
            command = [str(args.cwebp.resolve()), '-quiet', '-z', '9', '-near_lossless', str(level)]
            if level == 100:
                command.append('-exact')
            command += [str(source_png), '-o', str(target)]
            subprocess.run(command, check=True, capture_output=True)
            encoded = target.read_bytes()
            decoded = rgba(qt_decode(encoded))
            if pixels.shape != decoded.shape or not np.array_equal(pixels[:, :, 3], decoded[:, :, 3]):
                raise ValueError('Dimensions or alpha changed')
            difference = np.abs(pixels[:, :, :3].astype(np.int16) - decoded[:, :, :3].astype(np.int16))
            mse = float(np.mean(difference.astype(np.float64) ** 2))
            identical = bool(np.array_equal(pixels, decoded))
            if level == 100 and not identical:
                raise ValueError('Lossless control changed pixels')
            result['records'].append(dict(
                file=source.as_posix(), sha256=hashlib.sha256(data).hexdigest(), webp_encoding=encoding,
                width=pixels.shape[1], height=pixels.shape[0], near_lossless=level,
                source_bytes=len(data), encoded_bytes=len(encoded),
                reduction_percent=round(100*(1-len(encoded)/len(data)), 2),
                rgba_identical=identical, alpha_identical=True,
                changed_pixels_percent=round(float(np.mean(np.any(difference != 0, axis=2))*100), 3),
                max_channel_error=int(difference.max()), mean_channel_error=round(float(difference.mean()), 4),
                p99_channel_error=float(np.percentile(difference, 99)),
                psnr_db=None if mse == 0 else round(10*math.log10(255**2/mse), 3),
                qt_webp_timing=baseline, candidate_timing=measure(lambda: qt_decode(encoded), args.repeat)))
            (output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
        if hashlib.sha256(source.read_bytes()).hexdigest() != hashlib.sha256(data).hexdigest():
            raise ValueError('Input changed during benchmark')
        print(f'{source.name}: {len(args.levels)} candidates measured', flush=True)


if __name__ == '__main__':
    main()
