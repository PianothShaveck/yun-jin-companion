#!/usr/bin/env python3
"""Rebuild verified 900×600 previews while preserving catalog IDs and original formats."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from PIL import Image, ImageChops
import pillow_jxl

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT/'app/assets'
pillow_jxl.JpegXLImagePlugin.DECODE_THREADS = 2


def error(left, right):
    if left.size != right.size:
        return 256
    a, b = left.convert('RGBA'), right.convert('RGBA')
    if a.getchannel('A') != b.getchannel('A'):
        if ImageChops.difference(a.getchannel('A'),b.getchannel('A')).getbbox():
            return 256
    return max(high for low, high in ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getextrema())


def build(assets=ASSETS, cwebp='cwebp'):
    assets=Path(assets)
    catalog_path=assets/'calendar-index.json'
    document=json.loads(catalog_path.read_text(encoding='utf-8'))
    for name,record in document['images'].items():
        if not re.fullmatch(r'(?:YJ-\d{3}|m\d{2}-[a-z])\.webp',name):
            raise ValueError('Invalid preview ID')
        file=record.get('file',name)
        if not re.fullmatch(r'(?:YJ-\d{3}|m\d{2}-[a-z])\.(?:webp|jxl)',file):
            raise ValueError('Invalid original file')
        source=assets/'calendar'/file
        if hashlib.sha256(source.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Original changed: '+file)
    with tempfile.TemporaryDirectory(prefix='yun-jin-previews-',dir=assets) as temporary:
        temporary=Path(temporary)
        for name,record in document['images'].items():
            source=assets/'calendar'/record.get('file',name)
            with Image.open(source) as original:
                reference=original.convert('RGBA').resize((900,600),Image.Resampling.LANCZOS)
            png=temporary/'reference.png';candidate=temporary/'candidate.webp';reference.save(png)
            subprocess.run([cwebp,'-quiet','-z','9','-near_lossless','60',str(png),'-o',str(candidate)],check=True)
            with Image.open(candidate) as image:
                if error(reference,image)>2:
                    raise ValueError('Preview exceeds pixel tolerance: '+name)
            target=assets/'calendar-preview'/name
            retain=False
            if target.is_file() and target.stat().st_size<=candidate.stat().st_size:
                with Image.open(target) as existing:retain=error(reference,existing)<=2
            if not retain:
                target.parent.mkdir(exist_ok=True)
                os.replace(candidate,target)
            record['preview_sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
        index=temporary/'index.json';index.write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
        os.replace(index,catalog_path)
    print(f"Verified {len(document['images'])} previews")


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,default=ASSETS)
    parser.add_argument('--cwebp',default='cwebp')
    args=parser.parse_args();build(args.assets,args.cwebp)
