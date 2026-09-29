#!/usr/bin/env python3
"""Build final runtime and optional source archives from explicit release roots."""
import argparse
from pathlib import Path
import zipfile
import hashlib
import json
import os
import tempfile
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'dist/Yun-Jin-Companion-1.1.0.zip'

def runtime_files():
    paths=[ROOT/name for name in ('Windows.cmd','Mac.command','Linux.sh','Guida.pdf')]
    for folder in ('app','installer'):
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo','.log','.zip')
                     and p.name!='release-manifest.json')
    return paths

def write_manifest():
    requirements={}
    for line in (ROOT/'installer/requirements.txt').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            name,version=line.strip().split('==');requirements[name]=version
    document=dict(protocol=1,version='1.1.0',python_min=[3,10],python_max_exclusive=[3,15],
                  requirements=requirements,files={str(p.relative_to(ROOT)).replace('\\','/'):
                      hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(runtime_files())})
    (ROOT/'app/release-manifest.json').write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')

def build(source=False):
    write_manifest()
    output=OUTPUT.with_name('Yun-Jin-Companion-1.1.0-Sorgenti.zip') if source else OUTPUT
    output.parent.mkdir(exist_ok=True)
    paths=[ROOT/name for name in ('Windows.cmd','Mac.command','Linux.sh','Guida.pdf')]
    if source:paths.extend(ROOT/name for name in ('README.md','.gitignore'))
    folders=('app','installer','docs','tests','tools','.github') if source else ('app','installer')
    for folder in folders:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo','.log','.zip'))
    fd,temporary=tempfile.mkstemp(prefix='release-',suffix='.zip',dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for path in sorted(paths):
                archive.write(path,Path('Yun-Jin-Companion-1.1.0')/path.relative_to(ROOT))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Archive CRC validation failed')
        # Windows fsync/_commit requires a writable file descriptor.
        with open(temporary,'r+b') as stream:os.fsync(stream.fileno())
        os.replace(temporary,output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(output)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',action='store_true',help='Also build the repository source ZIP')
    args=parser.parse_args()
    build()
    if args.source:build(source=True)

if __name__=='__main__':main()
