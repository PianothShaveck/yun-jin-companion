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
OUTPUT=ROOT/'dist/Yun-Jin-Companion-1.5.5.zip'
MAX_RUNTIME_ZIP = 2 * 1024 ** 3

# Only maintained sources belong in the repository archive. Working artwork,
# reviews, release history and publishing notes are not distribution sources.
SOURCE_FILES = (
    'README.md', '.gitignore', 'docs/build_guide.py',
    'tools/package_release.py', 'tools/prune_sprite_cache.py',
    'tools/build_sprite_cache.py', 'tools/render_guide_assets.py',
)
GUIDE_IMAGES = (
    'appunti.png', 'promemoria.png', 'avviso.png', 'voce.png',
    'metronomo.png', 'cronometro.png', 'focus.png', 'aggiornamento.png',
    'sonno-fasi.png', 'orario-meteo.png', 'conduct16.png', 'stopwatch16.png',
    'studio.png', 'carte.png', 'scorciatoie.png', 'meteo.png', 'calendario.png', 'sveglie.png',
)

def animation_sources():
    assets=ROOT/'app/assets'
    specs=json.loads((assets/'animations.json').read_text(encoding='utf-8'))['animations']
    return {assets/spec['file'] for spec in specs}

def write_animation_index():
    assets=ROOT/'app/assets';index={}
    for spec in json.loads((assets/'animations.json').read_text(encoding='utf-8'))['animations']:
        encoded=json.dumps(spec,sort_keys=True).encode('utf-8')
        digest=hashlib.sha256(b'yun-jin-normalized-v1\0'+encoded+(assets/spec['file']).read_bytes()).hexdigest()[:24]
        stem=spec['name']+'-'+digest
        if not (assets/'normalized'/(stem+'.webp')).is_file():
            raise ValueError('Rigenera la cache animazioni: '+spec['name'])
        index[hashlib.sha256(encoded).hexdigest()]=stem
    (assets/'normalized/index.json').write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')

def runtime_files():
    sources=animation_sources()
    paths=[ROOT/name for name in ('Windows.cmd','Mac.command','Linux.sh','Guida.pdf')]
    for folder in ('app','installer'):
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo','.log','.zip')
                     and p.name!='release-manifest.json' and p not in sources)
    return paths

def write_manifest():
    requirements={}
    for line in (ROOT/'installer/requirements.txt').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            name,version=line.strip().split('==');requirements[name]=version
    document=dict(protocol=1,version='1.5.5',python_min=[3,11],python_max_exclusive=[3,15],
                  requirements=requirements,files={str(p.relative_to(ROOT)).replace('\\','/'):
                      hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(runtime_files())})
    (ROOT/'app/release-manifest.json').write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')

def build(source=False):
    write_animation_index()
    write_manifest()
    output=OUTPUT.with_name('Yun-Jin-Companion-1.5.5-Sorgenti.zip') if source else OUTPUT
    output.parent.mkdir(exist_ok=True)
    paths=[ROOT/name for name in ('Windows.cmd','Mac.command','Linux.sh','Guida.pdf')]
    if source:
        paths.extend(ROOT/name for name in SOURCE_FILES)
        paths.extend(ROOT/'docs/art'/name for name in GUIDE_IMAGES)
    folders=('app','installer','tests','.github') if source else ('app','installer')
    for folder in folders:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo','.log','.zip'))
    if not source:
        sources=animation_sources();paths=[p for p in paths if p not in sources]
    fd,temporary=tempfile.mkstemp(prefix='release-',suffix='.zip',dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for path in sorted(paths):
                archive.write(path,Path('Yun-Jin-Companion-1.5.5')/path.relative_to(ROOT))
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Archive CRC validation failed')
        # Match the updater limit.
        if not source and Path(temporary).stat().st_size>MAX_RUNTIME_ZIP:
            raise ValueError('Il pacchetto supera il limite degli aggiornamenti automatici (2 GiB).')
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
    from prune_sprite_cache import prune
    prune()
    build()
    if args.source:build(source=True)

if __name__=='__main__':main()
