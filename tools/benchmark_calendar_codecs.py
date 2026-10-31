#!/usr/bin/env python3
"""Read-only JPEG XL experiment. No production assets or manifest are changed.

Requires the release's PyQt6/Qt versions plus numpy and imagecodecs (development
dependencies only). Timings are warm in-memory decodes, not application startup,
disk/network latency or native Windows/macOS measurements.
"""
import argparse
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import imagecodecs
import numpy as np
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, PYQT_VERSION_STR, qVersion
from PyQt6.QtGui import QImage, QImageReader


def webp_encoding(data):
    """Identify the bitstream; animated inputs need a separate sequence benchmark."""
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        raise ValueError('Expected a WebP RIFF container')
    offset, chunks = 12, set()
    while offset + 8 <= len(data):
        tag = data[offset:offset + 4]
        length = int.from_bytes(data[offset + 4:offset + 8], 'little')
        if offset + 8 + length > len(data):
            raise ValueError('Truncated WebP chunk')
        chunks.add(tag)
        offset += 8 + length + (length & 1)
    if chunks.intersection({b'ANIM', b'ANMF'}):
        raise ValueError('Animated WebP is outside this still-image benchmark')
    if b'VP8L' in chunks:
        return 'lossless'
    if b'VP8 ' in chunks:
        return 'lossy'
    raise ValueError('WebP image payload not found')


def qt_decode(data, fmt=b'webp'):
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer, fmt)
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString())
    return image


def rgba(image):
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    view = image.constBits()
    view.setsize(image.sizeInBytes())
    return np.frombuffer(view, np.uint8).reshape(image.height(), image.width(), 4).copy()


def jxl_decode(data, threads):
    pixels = np.ascontiguousarray(imagecodecs.jpegxl_decode(data, numthreads=threads))
    height, width, channels = pixels.shape
    fmt = QImage.Format.Format_RGB888 if channels == 3 else QImage.Format.Format_RGBA8888
    return QImage(pixels.data, width, height, pixels.strides[0], fmt).copy()


def measure(call, repeat):
    call()  # warm codec dispatch; the first invocation is not a startup benchmark
    samples, cpu_samples = [], []
    for _ in range(repeat):
        start = time.perf_counter()
        cpu_start = time.process_time()
        image = call()
        cpu_samples.append((time.process_time() - cpu_start) * 1000)
        samples.append((time.perf_counter() - start) * 1000)
        if image.isNull():
            raise ValueError('Decoder returned no image')
    return dict(wall_ms_median=round(statistics.median(samples), 3),
                wall_ms_min=round(min(samples), 3), wall_ms_max=round(max(samples), 3),
                process_cpu_ms_median=round(statistics.median(cpu_samples), 3),
                wall_ms_samples=[round(x, 3) for x in samples],
                process_cpu_ms_samples=[round(x, 3) for x in cpu_samples])


def benchmark(paths, efforts, repeat, threads, decoding_speed):
    records = []
    for path in paths:
        data = path.read_bytes()
        encoding = webp_encoding(data)
        original = qt_decode(data)
        pixels = rgba(original)
        # Opaque calendar files need no alpha channel. Keep actual transparency.
        array = pixels[:, :, :3].copy() if np.all(pixels[:, :, 3] == 255) else pixels
        webp_timing = measure(lambda: qt_decode(data), repeat)
        for effort in efforts:
            start = time.perf_counter()
            encoded = imagecodecs.jpegxl_encode(array, lossless=True, effort=effort,
                                               numthreads=threads, decodingspeed=decoding_speed)
            encode_ms = (time.perf_counter() - start) * 1000
            identical = np.array_equal(pixels, rgba(jxl_decode(encoded, threads)))
            if not identical:
                raise ValueError(f'Pixels changed: {path}')
            jxl_timing = measure(lambda: jxl_decode(encoded, threads), repeat)
            records.append(dict(file=path.as_posix(), sha256=hashlib.sha256(data).hexdigest(),
                                width=original.width(), height=original.height(), effort=effort,
                                webp_bytes=len(data), jxl_bytes=len(encoded), webp_encoding=encoding,
                                reduction_percent=round((1-len(encoded)/len(data))*100, 2),
                                rgba_identical=bool(identical),
                                qt_webp_decode_ms=webp_timing['wall_ms_median'],
                                jxl_to_qimage_decode_ms=jxl_timing['wall_ms_median'],
                                qt_webp_timing=webp_timing, jxl_to_qimage_timing=jxl_timing,
                                jxl_encode_ms=round(encode_ms, 3)))
    return dict(platform=platform.platform(), python=platform.python_version(),
                qt=qVersion(), pyqt=PYQT_VERSION_STR, imagecodecs=imagecodecs.__version__,
                jxl=imagecodecs.jpegxl_version(), threads_jxl=threads, repetitions=repeat,
                decoding_speed=decoding_speed,
                qt_read_formats=[bytes(x).decode() for x in QImageReader.supportedImageFormats()],
                limitations=['warm in-memory decoding only; QPixmap creation excluded',
                             'JPEG XL adapter includes numpy-to-QImage ownership copy',
                             'process CPU time sums worker threads; not energy or battery measurement',
                             'peak decoder memory and cold imports not measured',
                             'no native JPEG XL Qt plugin or Windows/macOS execution',
                             'RGBA pixel equality checked; ICC/EXIF metadata not migrated',
                             'selected calendar still images, not a population estimate'],
                records=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--effort', nargs='+', type=int, choices=range(1, 10), default=[5, 7])
    parser.add_argument('--repeat', type=int, default=11)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--decoding-speed', type=int, choices=range(5), default=0)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error('--repeat must be positive')
    if args.threads < 1:
        parser.error('--threads must be positive')
    if args.output.resolve() in {p.resolve() for p in args.files}:
        parser.error('output must not overwrite an input')
    result = benchmark(args.files, args.effort, args.repeat, args.threads, args.decoding_speed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'{len(result["records"])} results; all decoded RGBA pixels unchanged')


if __name__ == '__main__':
    main()
