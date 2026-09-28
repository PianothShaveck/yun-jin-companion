#!/usr/bin/env python3
"""Render QA previews using the exact runtime sprite loader, without asset edits."""
import os,sys,json,base64
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QRegion
from yun_jin_core import SpriteSheet,ANIMATIONS
from PIL import Image,ImageDraw
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'dist/animation-review'
OUT.mkdir(parents=True,exist_ok=True);frames_dir=OUT/'frames';frames_dir.mkdir(exist_ok=True)
app=QApplication([]);sheet=SpriteSheet(ROOT/'app/spritesheet-yun-jin-v2.png')
sheet.frames[0,5].save(str(frames_dir/'original.png'))
manifest=json.loads((ROOT/'app/assets/animations.json').read_text())
clips=[]
references=[]
for name,label in [('idle','Riposo originale'),('right','Corsa a destra originale'),
                   ('left','Corsa a sinistra originale'),('jump','Salto originale'),
                   ('failed','A terra originale')]:
 if name not in ANIMATIONS:continue
 key,count,timing=ANIMATIONS[name]
 item={'name':name,'label':label,'timing':timing,'frames':[]}
 for i in range(count):
  path=frames_dir/f'original-{name}-{i:02}.png';sheet.frames[key,i].save(str(path))
  item['frames'].append('data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode())
 references.append(item)
for spec in manifest['animations']:
 key,count,timing=ANIMATIONS[spec['name']]
 clip={'name':spec['name'],'label':spec['label'],'timing':timing,'frames':[]}
 contact=Image.new('RGB',(800,850),'#40434b');d=ImageDraw.Draw(contact)
 for i in range(count):
  pic=sheet.frames[key,i];path=frames_dir/f'{spec["name"]}-{i:02}.png';pic.save(str(path))
  image=Image.open(path).convert('RGBA');x=(i%4)*200;y=(i//4)*210
  contact.paste(image,(x+14,y+23),image);d.text((x+16,y+4),str(i+1),fill='white')
  clip['frames'].append('data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode())
  box=QRegion(pic.mask()).boundingRect()
  minimum_height=174*spec.get('pose_height_range',[.80,1.16])[0]
  if box.width()<50 or box.height()<minimum_height:raise ValueError(f'{spec["name"]} {i}: unexpected scale')
  if box.left()<1 or box.top()<1 or box.right()>=pic.width()-1 or box.bottom()>=pic.height()-1:
   raise ValueError(f'{spec["name"]} {i}: frame touches canvas edge')
 contact.save(OUT/f'{spec["name"]}-contact.png');clips.append(clip)
 print(spec['name'],count,'frames checked')
(OUT/'preview-data.json').write_text(json.dumps({'original':'data:image/png;base64,'+base64.b64encode((frames_dir/'original.png').read_bytes()).decode(),'references':references,'clips':clips}))
