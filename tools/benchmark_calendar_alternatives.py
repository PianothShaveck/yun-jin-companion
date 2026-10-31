#!/usr/bin/env python3
"""Read-only lossless alternatives experiment; outputs metrics, never replaces art.

Uses development-only Pillow, imagecodecs, numpy and PyQt6. Pixel mismatches are
recorded as failures, not accepted as size/speed wins. Native deployment, energy,
metadata round trips, peak memory and animated images are outside this test.
"""
import argparse
import hashlib
import io
import json
import platform
import time
from pathlib import Path

import imagecodecs as ic
import numpy as np
from PIL import Image, __version__ as pillow_version, features
from PyQt6.QtCore import PYQT_VERSION_STR, qVersion
from PyQt6.QtGui import QImage

from benchmark_calendar_codecs import qt_decode, rgba, measure, jxl_decode, webp_encoding


def owned_image(pixels):
    pixels = np.ascontiguousarray(pixels)
    h, w, channels = pixels.shape
    fmt = QImage.Format.Format_RGB888 if channels == 3 else QImage.Format.Format_RGBA8888
    return QImage(pixels.data, w, h, pixels.strides[0], fmt).copy()


def pillow_encode(pixels, fmt):
    buffer = io.BytesIO()
    options = dict(lossless=True, quality=100, method=6, exact=True) if fmt == 'WEBP' else dict(optimize=True, compress_level=9)
    Image.fromarray(pixels).save(buffer, fmt, **options)
    return buffer.getvalue()


def codecs(threads):
    return {
        'webp-max': (lambda a: pillow_encode(a, 'WEBP'), qt_decode,
                     dict(lossless=True, quality=100, method=6, exact=True, decoder='Qt WebP')),
        'jxl-speed1': (lambda a: ic.jpegxl_encode(a, lossless=True, effort=7, numthreads=threads, decodingspeed=1),
                       lambda b: jxl_decode(b, threads), dict(lossless=True, effort=7, decoding_speed=1, threads=threads)),
        'jxl-speed2': (lambda a: ic.jpegxl_encode(a, lossless=True, effort=7, numthreads=threads, decodingspeed=2),
                       lambda b: jxl_decode(b, threads), dict(lossless=True, effort=7, decoding_speed=2, threads=threads)),
        'png': (lambda a: pillow_encode(a, 'PNG'), lambda b: qt_decode(b, b'png'),
                dict(optimize=True, compress_level=9, decoder='Qt PNG')),
        'avif': (lambda a: ic.avif_encode(a, level=100, speed=6, bitspersample=8,
                                        pixelformat=ic.AVIF.PIXEL_FORMAT.YUV444,
                                        matrix=ic.AVIF.MATRIX_COEFFICIENTS.IDENTITY,
                                        codec=ic.AVIF.CODEC_CHOICE.AOM, numthreads=threads),
                 lambda b: owned_image(ic.avif_decode(b, numthreads=threads)),
                 dict(quality=100, speed=6, depth=8, chroma='444', matrix='identity', encoder='aom', threads=threads)),
        'jpegls': (lambda a: ic.jpegls_encode(a, level=0), lambda b: owned_image(ic.jpegls_decode(b)),
                   dict(near_lossless_error=0, decoder='CharLS + QImage copy')),
        'qoi': (ic.qoi_encode, lambda b: owned_image(ic.qoi_decode(b)), dict(decoder='QOI + QImage copy')),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--codecs', nargs='+', choices=list(codecs(4)), default=list(codecs(4)))
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--repeat', type=int, default=11)
    args = parser.parse_args()
    if args.threads < 1 or args.repeat < 1:
        parser.error('threads and repeat must be positive')
    if args.output.resolve() in {p.resolve() for p in args.files}:
        parser.error('output must not overwrite an input')
    records = []
    result = dict(platform=platform.platform(), python=platform.python_version(),
                  qt=qVersion(), pyqt=PYQT_VERSION_STR, imagecodecs=ic.__version__,
                  pillow=pillow_version, pillow_webp=features.version('webp'),
                  versions={n: getattr(ic, n + '_version')() for n in ['jpegxl', 'avif', 'webp', 'jpegls', 'qoi']},
                  repetitions=args.repeat, records=records,
                  limitations=['warm in-memory decoding; QPixmap conversion excluded',
                               'non-Qt decoders include ownership copy to QImage',
                               'process CPU sums threads, not an energy measurement',
                               'no cold import, native Windows/macOS, peak RAM or metadata round-trip tests',
                               'selected still images, not population estimate'])
    available = codecs(args.threads)
    for path in args.files:
        source = path.read_bytes()
        encoding = webp_encoding(source)
        pixels = rgba(qt_decode(source))
        array = pixels[:, :, :3].copy() if np.all(pixels[:, :, 3] == 255) else pixels
        baseline = measure(lambda: qt_decode(source), args.repeat)
        for name in args.codecs:
            encode, decode, settings = available[name]
            record = dict(file=path.as_posix(), sha256=hashlib.sha256(source).hexdigest(),
                          webp_encoding=encoding, width=pixels.shape[1], height=pixels.shape[0],
                          codec=name, settings=settings, source_bytes=len(source),
                          qt_webp_timing=baseline)
            try:
                start = time.perf_counter()
                encoded = encode(array)
                record['encode_ms'] = round((time.perf_counter()-start)*1000, 3)
                decoded = rgba(decode(encoded))
                identical = np.array_equal(pixels, decoded)
                record.update(encoded_bytes=len(encoded), rgba_identical=bool(identical),
                              reduction_percent=round(100*(1-len(encoded)/len(source)), 2))
                if identical:
                    record['decode_timing'] = measure(lambda: decode(encoded), args.repeat)
                else:
                    record['error'] = 'Decoded RGBA differs; candidate rejected'
            except Exception as exc:
                record['error'] = f'{type(exc).__name__}: {exc}'
            records.append(record)
            # Checkpoint after each result; interruption leaves useful metrics.
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(f'{path.name}: {len(args.codecs)} candidates checked', flush=True)
    failures = sum('error' in r for r in records)
    print(f'{len(records)} results; {failures} failed or unsupported candidates')


if __name__ == '__main__':
    main()
