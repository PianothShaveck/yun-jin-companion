#!/usr/bin/env python3
"""Measure rendered alpha silhouettes and make equal-scale reference pairs."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

NAMES = [('morning16', 'Buongiorno'), ('afternoon16', 'Buon pomeriggio'),
         ('evening16', 'Buona sera'), ('greeting16', 'Inchino'),
         ('yawn16', 'Sbadiglio'), ('sun16', 'Al sole'), ('cloud16', 'Nuvoloso'),
         ('rain16', 'Pioggia'), ('snow16', 'Neve'), ('applause16', 'Applauso')]


def metrics(image):
    alpha = np.asarray(image.convert('RGBA'))[:, :, 3]/255
    ys, xs = np.where(alpha > 80/255)
    top, bottom = int(ys.min()), int(ys.max())+1
    height = bottom-top
    result = dict(height=height, silhouette=int(xs.max()-xs.min()+1))
    for label, low, high in [('head', 0, .28), ('skirt', .6, .8), ('boots', .86, 1)]:
        selected = xs[(ys >= top+round(low*height)) & (ys < top+round(high*height))]
        result[label] = int(selected.max()-selected.min()+1)
    result['boot_area'] = round(float(alpha[bottom-30:bottom].sum()), 2)
    result['toe_area'] = round(float(alpha[bottom-14:bottom].sum()), 2)
    return result


def build(review, output):
    frames = Path(review)/'frames'; output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    original = Image.open(frames/'original.png').convert('RGBA')
    report = {'reference': metrics(original), 'animations': {},
              'method': 'Actual runtime PNGs; alpha > 80 for bounds; alpha-weighted areas. '
                        'Head/skirt bands and 30/14-pixel bottom bands are screening '
                        'measurements, not semantic body segmentation. Resting-pose '
                        'ratios are checked separately from bent or turned poses.'}
    canvas = Image.new('RGB', (1504, 84+456*((len(NAMES)+1)//2)), '#eeebf3'); draw = ImageDraw.Draw(canvas)
    try:
        title = ImageFont.truetype('DejaVuSans.ttf', 27)
        font = ImageFont.truetype('DejaVuSans.ttf', 18)
    except OSError:
        title = font = ImageFont.load_default()
    draw.text((24, 16), 'Yun Jin Companion 1.2.1 · confronto delle proporzioni', fill='#362844', font=title)
    for index, (name, label) in enumerate(NAMES):
        pics = [Image.open(frames/f'{name}-{i:02}.png').convert('RGBA') for i in range(16)]
        report['animations'][name] = [metrics(p) for p in pics]
        x, y = 16+(index % 2)*744, 68+(index//2)*456
        draw.rounded_rectangle((x, y, x+728, y+440), radius=14, fill='#faf8fc', outline='#dbd3e4')
        draw.text((x+18, y+12), label, fill='#362844', font=font)
        for col, (pic, text) in enumerate([(original, 'Originale'), (pics[0], 'Revisione')]):
            draw.text((x+24+col*364, y+40), text, fill='#786987', font=font)
            scaled = pic.resize((342, 372), Image.Resampling.NEAREST)
            canvas.paste(scaled, (x+10+col*364, y+65), scaled)
    (output/'proportions.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    canvas.save(output/'Confronto-1.2.1.png')
    print(output/'Confronto-1.2.1.png')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review'); parser.add_argument('output')
    args = parser.parse_args(); build(args.review, args.output)
