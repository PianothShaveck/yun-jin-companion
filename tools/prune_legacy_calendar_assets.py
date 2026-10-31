"""Remove only the old managed calendar filenames after a source update."""
from pathlib import Path
import json


def prune(root):
    root = Path(root).resolve()
    try:
        records = json.loads((root/'app/assets/calendar-index.json').read_text())['images']
        canonical = {f'YJ-{number:03d}.webp' for number in range(1, 745)}
        if not records or not set(records).issubset(canonical):
            return []
        originals = {record['file'] for record in records.values()}
    except (OSError, ValueError, KeyError, TypeError):
        return []
    counts = (6, 7, 6, 6, 7, 9, 9, 9, 6, 6, 7, 6)
    removed = []
    for directory in ('calendar', 'calendar-preview'):
        folder = root/'app/assets'/directory
        # A linked asset directory may point to personal files elsewhere.
        if any(part.is_symlink() for part in (root/'app', root/'app/assets', folder)):
            continue
        obsolete = []
        for month, count in enumerate(counts, 1):
            for letter in 'abcdefghi'[:count]:
                obsolete.append(f'm{month:02d}-{letter}.webp')
        if directory == 'calendar':
            # The published checkout used WebP originals before the verified
            # JXL conversion. Keep the currently indexed codec for every ID.
            obsolete.extend(f'YJ-{number:03d}{suffix}' for number in range(1, 745)
                            for suffix in ('.webp', '.jxl')
                            if f'YJ-{number:03d}{suffix}' not in originals)
        for name in obsolete:
            path = folder/name
            if path.is_file() and not path.is_symlink():
                path.unlink()
                removed.append(path)
    return removed


if __name__ == '__main__':
    prune(Path(__file__).resolve().parents[1])
