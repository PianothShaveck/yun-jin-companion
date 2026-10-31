#!/usr/bin/env python3
"""Build a resumable, verified calendar candidate set without replacing assets.

Originals: choose the smallest of the existing WebP and lossless JXL.
Previews: try near-lossless 60 only for opaque VP8L inputs, keep only smaller
files with <=2/255 channel error. Visual approval and runtime JXL integration
remain separate. Requires development-only numpy, imagecodecs, Pillow, Qt,
and cwebp; no dependencies are added to the application.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import multiprocessing
from pathlib import Path
import subprocess
import tempfile
import time

import imagecodecs as ic
import numpy as np
from PIL import Image
from PyQt6.QtCore import qVersion
from benchmark_calendar_codecs import qt_decode, rgba, webp_encoding, jxl_decode


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_bytes(data)
    temp.replace(path)


def metadata(data):
    tags, offset = [], 12
    while offset + 8 <= len(data):
        tag = data[offset:offset + 4]
        size = int.from_bytes(data[offset + 4:offset + 8], 'little')
        if tag not in (b'VP8 ', b'VP8L', b'VP8X', b'ALPH'):
            tags.append(tag.decode('ascii', errors='replace'))
        offset += 8 + size + (size & 1)
    return tags


def webp_encode(pixels, cwebp, level):
    with tempfile.TemporaryDirectory(prefix='yj-codec-') as tmp:
        source, target = Path(tmp)/'input.png', Path(tmp)/'output.webp'
        Image.fromarray(pixels).save(source)
        command = [cwebp, '-quiet', '-z', '9', '-near_lossless', str(level)]
        if level == 100:
            command.append('-exact')
        subprocess.run(command + [str(source), '-o', str(target)], check=True, capture_output=True)
        return target.read_bytes()


def original_candidate(data, config):
    encoding = webp_encoding(data)
    pixels = rgba(qt_decode(data))
    selected, extension = data, '.webp'
    details = dict(source_bytes=len(data), encoding=encoding, metadata=metadata(data),
                   width=pixels.shape[1], height=pixels.shape[0], candidates={})
    # Do not silently discard a color profile/orientation/other metadata.
    if details['metadata']:
        details['retained_reason'] = 'Metadata preservation requires separate support'
    else:
        details['candidates']['webp'] = len(data)
        array = pixels[:, :, :3].copy() if np.all(pixels[:, :, 3] == 255) else pixels
        candidate = ic.jpegxl_encode(array, lossless=True, effort=7,
                                    decodingspeed=0, numthreads=config['threads'])
        if not np.array_equal(pixels, rgba(jxl_decode(candidate, config['threads']))):
            raise ValueError('Lossless JXL changed RGBA pixels')
        details['candidates']['jxl'] = len(candidate)
        if len(candidate) < len(selected):
            selected, extension = candidate, '.jxl'
    details.update(selected_bytes=len(selected), rgba_identical=True, extension=extension)
    return selected, details


def preview_candidate(data, config):
    encoding = webp_encoding(data)
    pixels = rgba(qt_decode(data))
    selected = data
    details = dict(source_bytes=len(data), encoding=encoding, metadata=metadata(data),
                   width=pixels.shape[1], height=pixels.shape[0], max_channel_error=0,
                   alpha_identical=True, changed=False)
    if encoding != 'lossless':
        details['retained_reason'] = 'Existing lossy preview retained byte for byte'
    elif details['metadata'] or not np.all(pixels[:, :, 3] == 255):
        details['retained_reason'] = 'Metadata/transparency requires separate validation'
    else:
        candidate = webp_encode(pixels, config['cwebp'], 60)
        decoded = rgba(qt_decode(candidate))
        if decoded.shape != pixels.shape or not np.array_equal(decoded[:, :, 3], pixels[:, :, 3]):
            raise ValueError('Preview dimensions/alpha changed')
        diff = np.abs(pixels[:, :, :3].astype(np.int16) - decoded[:, :, :3].astype(np.int16))
        error = int(diff.max())
        details.update(candidate_bytes=len(candidate), candidate_max_channel_error=error)
        if len(candidate) < len(data) and error <= 2:
            selected = candidate
            mse = float(np.mean(diff.astype(np.float64)**2))
            details.update(changed=True, max_channel_error=error,
                           psnr_db=None if not mse else round(10*np.log10(255**2/mse), 3))
        else:
            details['retained_reason'] = 'Candidate larger or exceeds channel-error guard'
    details['selected_bytes'] = len(selected)
    return selected, details


def process_file(task):
    assets, output, name, expected, config = task
    assets, output = Path(assets), Path(output)
    original = (assets/'calendar'/name).read_bytes()
    preview = (assets/'calendar-preview'/name).read_bytes()
    hashes = dict(original=sha(original), preview=sha(preview))
    if hashes != dict(original=expected['sha256'], preview=expected['preview_sha256']):
        raise ValueError('Catalog hash mismatch: '+name)
    record_path = output/'records'/(Path(name).stem+'.json')
    if record_path.exists():
        previous = json.loads(record_path.read_text())
        if previous['config'] == config and previous['input_sha256'] == hashes:
            if all((output/previous[k]['file']).is_file() and
                   sha((output/previous[k]['file']).read_bytes()) == previous[k]['sha256']
                   for k in ('original', 'preview')):
                return previous
    start = time.monotonic()
    full, full_record = original_candidate(original, config)
    small, small_record = preview_candidate(preview, config)
    for kind, data, record, folder, ext in (
            ('original', full, full_record, 'originals', full_record['extension']),
            ('preview', small, small_record, 'previews', '.webp')):
        path = Path(folder)/(Path(name).stem+ext)
        atomic(output/path, data)
        record.update(file=path.as_posix(), sha256=sha(data))
    if sha((assets/'calendar'/name).read_bytes()) != hashes['original'] or sha((assets/'calendar-preview'/name).read_bytes()) != hashes['preview']:
        raise ValueError('Source changed during conversion: '+name)
    record = dict(name=name, config=config, input_sha256=hashes, original=full_record,
                  preview=small_record, seconds=round(time.monotonic()-start, 3))
    atomic(record_path, (json.dumps(record, indent=2)+'\n').encode())
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=Path(__file__).resolve().parents[1]/'app/assets')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cwebp', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--limit', type=int, help='Smoke test only; omit for complete catalog')
    args = parser.parse_args()
    if args.workers < 1 or args.threads < 1 or (args.limit is not None and args.limit < 1):
        parser.error('workers, threads and limit must be positive')
    assets, output = args.assets.resolve(), args.output.resolve()
    if output.is_relative_to(assets) or assets.is_relative_to(output):
        parser.error('output must be separate from assets')
    doc = json.loads((assets/'calendar-index.json').read_text())
    if doc['protocol'] != 1:
        parser.error('unsupported source catalog')
    names = sorted(doc['images'])[:args.limit]
    config = dict(protocol=1, cwebp=str(args.cwebp.resolve()),
                  cwebp_version=subprocess.check_output([str(args.cwebp.resolve()), '-version'], text=True).strip(),
                  jxl=ic.jpegxl_version(), qt=qVersion(), threads=args.threads,
                  original='smallest verified existing-webp/jxl-lossless-e7-speed0', preview='near60-opaque-vp8l-maxerror2')
    tasks = [(str(assets), str(output), name, doc['images'][name], config) for name in names]
    records, errors = [], []
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn')) as pool:
        pending = {pool.submit(process_file, task):task[2] for task in tasks}
        for future in as_completed(pending):
            name = pending[future]
            try:
                records.append(future.result())
            except Exception as exc:
                errors.append(dict(name=name, error=str(exc)))
            if (len(records)+len(errors)) % 25 == 0 or errors:
                print(f'{len(records)}/{len(names)} verified; {len(errors)} failures', flush=True)
    summary = dict(config=config, source_catalog_count=len(doc['images']), processed=len(records),
                   complete=len(records)==len(doc['images']) and not errors, errors=errors,
                   visual_review_complete=False, runtime_migrated=False,
                   records=sorted(records, key=lambda r:r['name']))
    for kind in ('original', 'preview'):
        before = sum(r[kind]['source_bytes'] for r in records)
        after = sum(r[kind]['selected_bytes'] for r in records)
        summary[kind] = dict(before=before, after=after, saved=before-after,
                             reduction_percent=round(100*(1-after/before), 3) if before else 0)
    summary['jxl_selected'] = sum(r['original']['extension']=='.jxl' for r in records)
    summary['previews_changed'] = sum(r['preview']['changed'] for r in records)
    atomic(output/'selection.json', (json.dumps(summary, indent=2)+'\n').encode())
    print(json.dumps({k:v for k,v in summary.items() if k not in ('config','records')}, indent=2), flush=True)
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
