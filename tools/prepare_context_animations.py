"""Pack reviewed generated poses with fixed clip scale and transparent gutters.

Build-time only: Pillow, numpy, scipy. No runtime dependencies are added.
The original and all previously approved animation assets are left untouched.
"""
from pathlib import Path
import json
import argparse
import io
import shutil
import numpy as np
from PIL import Image
from scipy.ndimage import label, find_objects, binary_dilation, distance_transform_edt

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'morning': 'Buongiorno', 'greeting': 'Inchino', 'afternoon': 'Buon pomeriggio', 'evening': 'Buona sera', 'yawn': 'Sbadiglio',
         'sun': 'Al sole', 'rain': 'Pioggia', 'snow': 'Neve', 'cloud': 'Nuvoloso', 'applause': 'Applauso'}
# Hold the reviewed bow pose; omit two drawings with enlarged shoes.
# Hold the end of the yawn briefly instead of using a wrong-arm drawing.
ORDERS = {'greeting': [0, 1, 2, 4, 3, 5, 8, 8, 8, 9, 10, 11, 13, 14, 14, 0],
          'yawn': [0, 1, 2, 3, 4, 5, 6, 6, 6, 9, 10, 11, 13, 13, 14, 0],
          'cloud': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 3, 2, 1, 0]}


def prepare(names=None):
    selected={n:t for n,t in NAMES.items() if not names or n in names}
    specs = json.loads((ROOT/'app/assets/animations.json').read_text())
    specs['animations'] = [s for s in specs['animations'] if s['name'] not in {n+'16' for n in selected}]
    clean = ROOT/'docs/context-art/ungraded'; clean.mkdir(exist_ok=True)
    report_path=ROOT/'docs/context-art/packing.json'
    report=json.loads(report_path.read_text()) if report_path.exists() else {}
    for name, title in selected.items():
        a = np.array(Image.open(ROOT/f'docs/context-art/generated/{name}.png').convert('RGBA'))
        rgb = a[:, :, :3].astype(float)
        high, low = rgb.max(axis=2), rgb.min(axis=2)
        # Transparent-image export debris: pure neon chroma absent from costume.
        fringe = (high > 220) & (low < 8) & ((high-low)/np.maximum(high, 1) > .94)
        a[fringe, 3] = 0
        ids, _ = label(a[:, :, 3] > 32, np.ones((3, 3)))
        sizes = np.bincount(ids.ravel()); sizes[0] = 0
        valid = sizes >= 18
        a[~binary_dilation(valid[ids]), 3] = 0
        ids, _ = label(a[:, :, 3] > 80, np.ones((3, 3)))
        sizes = np.bincount(ids.ravel()); sizes[0] = 0
        boxes = find_objects(ids)
        largest = sorted(np.argsort(sizes)[-16:], key=lambda k: (boxes[k-1][0].start+boxes[k-1][0].stop)/2)
        ordered = []
        for row in range(4):
            ordered.extend(sorted(largest[row*4:row*4+4], key=lambda k: boxes[k-1][1].start))
        centers = np.array([[(boxes[k-1][1].start+boxes[k-1][1].stop)/2,
                             (boxes[k-1][0].start+boxes[k-1][0].stop)/2] for k in ordered])
        # Grid rows are not assumed to be exact: some generated feet straddle
        # nominal cell boundaries. Separate complete connected characters first.
        yy, xx = np.indices(ids.shape)
        ownership = np.argmin((xx[:, :, None]-centers[:, 0])**2 +
                              (yy[:, :, None]-centers[:, 1])**2, axis=2)
        for i, ident in enumerate(ordered): ownership[ids == ident] = i
        # Low-alpha antialias pixels inherit the nearest opaque component, so a
        # neighbouring hat edge cannot become debris beneath another frame.
        nearest = distance_transform_edt(ids == 0, return_distances=False, return_indices=True)
        ownership = ownership[nearest[0], nearest[1]]
        floors = [boxes[k-1][0].stop for k in ordered]
        row_floors = [round(np.median(floors[r*4:r*4+4])) for r in range(4)]
        feet = []
        for k in ordered:
            b = boxes[k-1]; mask = (ids == k) & (yy >= b[0].stop-25)
            feet.append(float(np.median(xx[mask])))
        col_centers = [round(np.median(feet[c::4])) for c in range(4)]
        neutral_height = float(np.median([floors[i]-boxes[ordered[i]-1][0].start for i in (0, 1, 14, 15)]))
        # The rain model is a little larger in head and boots despite a narrow
        # skirt. A 4% uniform camera correction matches these parts together;
        # it applies equally to x/y and every pose, never squeezing the drawing.
        camera_scale = {'rain': .96, 'evening': .99, 'greeting': .975}.get(name, 1.0)
        frames = []
        for i in range(16):
            selected = (ownership == i) & (a[:, :, 3] > 0)
            if name == 'afternoon':
                # This greeting has no detached props. Keep each complete
                # character and its alpha edge, discard floating export strokes.
                selected &= binary_dilation(ids == ordered[i], iterations=2)
            ys, xs = np.where(selected)
            x0, x1, y0, y1 = xs.min(), xs.max()+1, ys.min(), ys.max()+1
            crop = a[y0:y1, x0:x1].copy()
            crop[~selected[y0:y1, x0:x1], 3] = 0
            target = Image.new('RGBA', (512, 512))
            # These gestures keep their feet on the ground. Use the
            # actual sole baseline, so grid spacing cannot cause vertical jitter.
            offset = (256+x0-col_centers[i%4], 440+y0-floors[i])
            assert min(offset) >= 0 and offset[0]+crop.shape[1] < 512 and offset[1]+crop.shape[0] < 512
            target.alpha_composite(Image.fromarray(crop), offset)
            frames.append(target)
        atlas = Image.new('RGBA', (2048, 2048))
        # Reuse the opening rest pose to close the loop without model drift.
        order = ORDERS.get(name, list(range(15))+[0])
        for i, source in enumerate(order): atlas.alpha_composite(frames[source], (i%4*512, i//4*512))
        filename = name+'-16.png'
        buffer=io.BytesIO(); atlas.save(buffer, format="PNG", optimize=True)
        (clean/filename).write_bytes(buffer.getvalue())
        Image.open(clean/filename).load()
        shutil.copy2(clean/filename, ROOT/'app/assets'/filename)
        # No single-frame flash: each gesture has preparation, a held phase and recovery.
        timing = [0.24, .21, .21, .24, .23, .23, .24, .27, .27, .24, .23, .23, .23, .23, .24, .28]
        if name == 'yawn': timing = [v*1.25 for v in timing]
        specs['animations'].append(dict(name=name+'16', label=title, file=filename,
            columns=4, rows=4, count=16, seconds_per_frame=timing, align_as_sequence=True,
            sequence_body_height=neutral_height/camera_scale, sequence_center=256, sequence_ground=440,
            pose_height_range=[.65, 1.16], art_revision='1.2.1-original-proportions'))
        report[name] = dict(neutral_height=neutral_height, camera_scale=camera_scale, row_floors=row_floors,
                            col_centers=col_centers, playback_source_order=order,
                            removed_neon_pixels=int(fringe.sum()))
    (ROOT/'app/assets/animations.json').write_text(json.dumps(specs, ensure_ascii=False, indent=2)+'\n')
    (ROOT/'docs/context-art/packing.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--names', nargs='+')
    prepare(parser.parse_args().names)
