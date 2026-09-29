#!/usr/bin/env python3
"""Pack reviewed sleep artwork without deforming, repainting or quantizing it.

All clips use one shared physical scale and floor. Waking follows the reviewed
seated-to-standing poses in reverse, avoiding anatomy drift between generators.
"""
from pathlib import Path
import json, shutil
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/source-art'
ASSETS=ROOT/'app/assets'
ENTRY_BOXES=[(86,45,385,507),(527,48,826,505),(964,83,1262,510),(1394,147,1702,510),
             (93,530,409,858),(528,549,848,859),(959,586,1294,858),(1400,586,1735,858)]
LOOP_BOXES=[(235,27,778,495),(878,31,1435,497),(233,523,780,996),(898,524,1458,994)]
# The final descent pose and loop have the same head size / physical dimensions.
LOOP_SCALE=0.581

def pack(source,boxes,factor=1.):
    image=Image.open(source).convert('RGBA');frames=[]
    for box in boxes:
        cell=image.crop(box)
        if factor!=1:
            cell=cell.resize((round(cell.width*factor),round(cell.height*factor)),Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(512,512))
        canvas.alpha_composite(cell,(round(256-cell.width/2),480-cell.height))
        frames.append(canvas)
    return frames

def sheet(frames,path):
    columns=4;rows=(len(frames)+3)//4
    image=Image.new('RGBA',(columns*512,rows*512))
    for i,frame in enumerate(frames):image.alpha_composite(frame,((i%4)*512,(i//4)*512))
    image.save(path,optimize=True)

def main():
    entry=pack(SOURCE/'sleep-enter.png',ENTRY_BOXES)
    loop=pack(SOURCE/'sleep-breathing.png',LOOP_BOXES,LOOP_SCALE)
    # Include the exact seam poses in the breathing cycle. Intermediate drawings
    # remain subtle; 0.8-1.1s holds produce a calm, roughly five-second breath.
    clips=[('sleep_in','Si addormenta',entry,[.38,.50,.45,.40,.45,.40,.50,.55]),
           ('sleep_loop','Dorme',[entry[-1],*loop,entry[-1]],[.85,.90,.95,.95,.90,.85]),
           ('sleep_out','Si sveglia',list(reversed(entry)),[.55,.45,.40,.45,.40,.45,.50,.38])]
    document=json.loads((ASSETS/'animations.json').read_text())
    document['animations']=[a for a in document['animations'] if not a['name'].startswith('sleep_')]
    for name,label,frames,timing in clips:
        filename=name.replace('_','-')+'.png';sheet(frames,ASSETS/filename)
        document['animations'].append(dict(name=name,label=label,file=filename,columns=4,rows=(len(frames)+3)//4,
            count=len(frames),seconds_per_frame=timing,align_as_sequence=True,
            sequence_body_height=456,sequence_center=256,sequence_ground=480,pose_height_range=[.5,1.1]))
    (ASSETS/'animations.json').write_text(json.dumps(document,indent=2)+'\n',encoding='utf-8')
    (ROOT/'docs/sleep-animation-packing.json').write_text(json.dumps(dict(
        entry_boxes=ENTRY_BOXES,loop_boxes=LOOP_BOXES,loop_uniform_scale=LOOP_SCALE,
        canvas=[512,512],ground=480,body_height=456,
        wake='Reverse of reviewed descent poses; identical anatomy at both seams.'),indent=2)+'\n')

if __name__=='__main__':main()
