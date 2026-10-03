#!/usr/bin/env python3
"""Remove obsolete generated sprite caches after overlaying a source patch."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prune(root=ROOT):
    assets = Path(root)/'app/assets'
    specs = json.loads((assets/'animations.json').read_text(encoding='utf-8'))['animations']
    expected = {}
    # Validate and compute every fingerprint before removing anything.
    for spec in specs:
        digest = hashlib.sha256(b'yun-jin-normalized-v1\0')
        digest.update(json.dumps(spec, sort_keys=True).encode('utf-8'))
        digest.update((assets/spec['file']).read_bytes())
        stem=spec['name']+'-'+digest.hexdigest()[:24]
        webp=assets/'normalized'/(stem+'.webp')
        expected[spec['name']] = stem+('.webp' if webp.is_file() else '.png')
    removed = []
    for path in list((assets/'normalized').iterdir()):
        match = re.fullmatch(r'(.+)-[0-9a-f]{24}\.(png|webp)', path.name)
        if match and match[1] in expected and path.name != expected[match[1]]:
            path.unlink(); removed.append(path.name)
    return removed


if __name__ == '__main__':
    print(f'{len(prune())} obsolete sprite caches removed.')
