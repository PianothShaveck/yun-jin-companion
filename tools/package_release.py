#!/usr/bin/env python3
"""Build final runtime and optional source archives from explicit release roots."""
import argparse
from pathlib import Path
import zipfile
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'dist/Yun-Jin-Companion-1.0.2.zip'

def build(source=False):
    output=OUTPUT.with_name('Yun-Jin-Companion-1.0.2-Sorgenti.zip') if source else OUTPUT
    output.parent.mkdir(exist_ok=True)
    paths=[ROOT/name for name in ('Windows.cmd','Mac.command','Linux.sh','Guida.pdf')]
    if source:paths.extend(ROOT/name for name in ('README.md','.gitignore'))
    folders=('app','installer','docs','tests','tools','.github') if source else ('app','installer')
    for folder in folders:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo','.log','.zip'))
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(paths):
            archive.write(path,Path('Yun-Jin-Companion-1.0.2')/path.relative_to(ROOT))
    print(output)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',action='store_true',help='Also build the repository source ZIP')
    args=parser.parse_args()
    build()
    if args.source:build(source=True)

if __name__=='__main__':main()
