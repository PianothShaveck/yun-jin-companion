#!/usr/bin/env python3
"""Identify complete sprites and author extraction metadata; never redraw pixels.
Developer tool only: requires Pillow, numpy, scipy. Runtime needs only PyQt6.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from scipy.ndimage import label,find_objects,distance_transform_edt
ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'app/assets'

def prepare():
    manifest=json.loads((ASSETS/'animations.json').read_text())
    report=[]
    for spec in manifest['animations']:
        image=np.array(Image.open(ASSETS/spec['file']).convert('RGBA'))
        alpha=image[:,:,3]
        if spec.get('packed_cells'):
            # Reviewed grids already contain their anchors, holds and jump lift.
            # Recentring individual drawings here would erase real movement.
            cw,ch=spec['frame_canvas']
            if image.shape[:2]!=(ch*spec['rows'],cw*spec['columns']):
                raise ValueError(f"{spec['name']}: packed atlas dimensions changed")
            heights=[]
            for i in range(spec['count']):
                c,r=i%spec['columns'],i//spec['columns']
                cell=alpha[r*ch:(r+1)*ch,c*cw:(c+1)*cw]
                ys,xs=np.where(cell>8)
                if not len(xs) or min(xs.min(),ys.min())<2 or xs.max()>=cw-2 or ys.max()>=ch-2:
                    raise ValueError(f"{spec['name']} frame {i}: clipped packed cell")
                heights.append(int(ys.max()-ys.min()+1))
            report.append({'name':spec['name'],'frames':spec['count'],
                           'height_range':[min(heights),max(heights)],
                           'reference_height':spec['sequence_body_height'],
                           'neighbor_intersections':0,'packed_anchors_preserved':True})
            continue
        labels,_=label(alpha>80,structure=np.ones((3,3)))
        areas=np.bincount(labels.ravel())
        distance,nearest=distance_transform_edt(labels==0,return_indices=True)
        ownership=labels[tuple(nearest)]
        bodies=[]
        for idx,sl in enumerate(find_objects(labels),1):
            if areas[idx]>2500:
                bodies.append((idx,[sl[1].start,sl[0].start,sl[1].stop,sl[0].stop]))
        if len(bodies)!=16:raise ValueError(f"{spec['name']}: expected 16 complete components, got {len(bodies)}")
        # Sort by rows, then columns; the source illustration need not be a perfect grid.
        bodies.sort(key=lambda b:(b[1][1]+b[1][3])/2)
        bodies=[b for row in range(4) for b in sorted(bodies[row*4:row*4+4],key=lambda b:(b[1][0]+b[1][2])/2)]
        heights=[b[1][3]-b[1][1] for b in bodies]
        body_height=float(np.median(heights))
        if min(heights)<body_height*.80:raise ValueError(f"{spec['name']}: possible truncated body")
        rects=[];offsets=[];clips=[]
        for i,(idx,box) in enumerate(bodies):
            x0,y0,x1,y1=box
            floor=y1
            main=labels[y0:y1,x0:x1]==idx
            centers=[]
            for row in range(round(main.shape[0]*.10),round(main.shape[0]*.30)):
                columns=np.flatnonzero(main[row])
                if len(columns):centers.append((columns[0]+columns[-1])/2+x0)
            if not centers:raise ValueError(f"{spec['name']} frame {i}: no head anchor")
            center=float(np.median(centers))
            x0=max(0,x0-2);y0=max(0,y0-2);x1=min(image.shape[1],x1+2);y1=min(image.shape[0],y1+2)
            # Retain antialias coverage around this figure only; exclude faint chroma debris.
            keep=(ownership[y0:y1,x0:x1]==idx)&(distance[y0:y1,x0:x1]<=1.5)&(alpha[y0:y1,x0:x1]>8)
            # Pixels belonging to another sprite are forbidden even within the padding.
            others=(labels[y0:y1,x0:x1]!=0)&(labels[y0:y1,x0:x1]!=idx)
            if np.any(keep & others):raise ValueError(f"{spec['name']} frame {i}: extraction mask intersects another figure")
            # Even faint retained pixels cannot be shared by two frame rectangles.
            for xx,yy,ww,hh in rects:
                if max(x0,xx)<min(x1,xx+ww) and max(y0,yy)<min(y1,yy+hh):
                    raise ValueError(f"{spec['name']} frame {i}: overlapping extraction rectangles")
            runs=[]
            for y,line in enumerate(keep):
                edges=np.diff(np.r_[False,line,False].astype(int))
                for start,end in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)):
                    runs.append([int(y),int(start),int(end-start)])
            rects.append([int(x0),int(y0),int(x1-x0),int(y1-y0)])
            offsets.append([int(round(256+x0-center)),int(450+y0-floor)])
            clips.append(runs)
        # Preserve the reviewed playback order and timings when repacking assets.
        for key in ('align_to_original','sequence_horizontal_scale'):spec.pop(key,None)
        spec.update(frame_rects=rects,frame_offsets=offsets,frame_canvas=[512,512],frame_clip_rows=clips,
                    align_as_sequence=True,sequence_body_height=body_height,sequence_ground=450,sequence_center=256)
        report.append({'name':spec['name'],'frames':16,'height_range':[min(heights),max(heights)],'reference_height':body_height,'neighbor_intersections':0})
    (ASSETS/'animations.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':'))+'\n')
    output=ROOT/'docs/animation-qa.json';output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':prepare()
