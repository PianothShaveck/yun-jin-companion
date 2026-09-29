"""Fit a restrained, time-invariant color finishing transform after art review."""
import os,sys,json,hashlib
from pathlib import Path
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion
from scipy.optimize import differential_evolution
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans
import argparse
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--review',type=Path,required=True,help='Output directory from render_animation_review.py before grading')
parser.add_argument('--source-assets',type=Path,required=True,help='Clean, ungraded animation PNG directory')
parser.add_argument('--names',nargs='+',help='Only recalibrate these animation names; all others remain unchanged')
parser.add_argument('--output',type=Path,default=ROOT/'docs/palette-calibration.json')
args=parser.parse_args()
sys.path.insert(0,str(ROOT/'tools'))
from color_match_animations import lab,rgb,transfer
QA=args.review;frames=QA/'frames'
reference=Image.open(ROOT/'app/spritesheet-yun-jin-v2.png').convert('RGBA')
def pixels(pic):
 a=np.array(pic);return a[:,:,:3][binary_erosion(a[:,:,3]>230)]/255.
reference_poses=[(c,0) for c in (0,2,3,5)]+[(1,1),(5,1),(2,2),(6,2),(1,4),(3,4),(3,5),(5,5)]
refs=[reference.crop((round(c*reference.width/8),round(r*reference.height/11),
                     round((c+1)*reference.width/8),round((r+1)*reference.height/11)))
      for c,r in reference_poses]
rpix=lab(np.concatenate([pixels(im) for im in refs]))
specs=json.loads((ROOT/'app/assets/animations.json').read_text())['animations']
if args.names:
 specs=[s for s in specs if s['name'] in args.names]
 if set(s['name'] for s in specs)!=set(args.names):raise ValueError('Unknown animation name')
spix=lab(np.concatenate([pixels(Image.open(frames/f'{s["name"]}-{i:02}.png').convert('RGBA')) for s in specs for i in range(s['count'])]))
rng=np.random.default_rng(71)
if len(spix)>120000:spix=spix[rng.choice(len(spix),120000,replace=False)]
def clusters(a):
 km=KMeans(n_clusters=24,random_state=11,n_init=5).fit(a)
 w=np.sqrt(np.bincount(km.labels_,minlength=24));return km.cluster_centers_,w/w.sum()
r,rw=clusters(rpix);s,sw=clusters(spix)
zero=[0,1,0,0,0,0,0,0]
def score(p,regularize=True):
 # Include gamut clipping in optimization instead of scoring impossible colors.
 v=lab(rgb(transfer(s,p)));dist=cdist(v,r)
 value=.5*(sw@dist.min(axis=1)+rw@dist.min(axis=0))
 if regularize:value+=.025*(p[0]**2+p[2]**2+p[3]**2)+3*(p[1]-1)**2+.006*p[4]**2+.7*np.sum(np.square(p[5:]))
 return float(value)
bounds=[(-3,3),(.85,1.05),(-2,2),(-2,2),(-4,4),(-.12,.12),(-.12,.12),(-.12,.12)]
trials=[]
for seed in (14,29,73):
 res=differential_evolution(score,bounds,seed=seed,popsize=14,maxiter=220,tol=1e-7)
 trials.append(res);print('trial',seed,'distance',score(res.x,False),flush=True)
res=min(trials,key=lambda v:v.fun);p=res.x
before,after=score(zero,False),score(p,False)
report={
 'parameters':p.tolist(),
 'parameter_names':['lightness_lift','chroma','a_balance','b_balance','hue_rotation_degrees','pink_chroma_adjustment','cyan_chroma_adjustment','purple_chroma_adjustment'],
 'distance_before':before,'distance_after':after,
 'method':f'One restrained smooth CIELAB transform shared by {len(specs)} selected sequences, applied only after art/anatomy/motion review. No quantization.',
 'metric':'Symmetric nearest-centroid Euclidean CIELAB distance; 24 k-means colors, square-root-frequency weights. Descriptive palette score, not a guarantee of perceptual equivalence.',
 'reference':f'Opaque interiors of 12 original idle/run/jump/fall poses; {sum(s["count"] for s in specs)} selected playback frames at actual runtime resolution.',
 'reference_poses_column_row':reference_poses,
 'animation_names':[s['name'] for s in specs],
 'original_spritesheet_sha256':hashlib.sha256((ROOT/'app/spritesheet-yun-jin-v2.png').read_bytes()).hexdigest(),
 'source_assets_sha256':{s['file']:hashlib.sha256((args.source_assets/s['file']).read_bytes()).hexdigest() for s in specs},
 'geometry':{'isotropic_scale':True,'reference_alpha_threshold':80,'same_transform_for_all_frames_in_sequence':True},
 'alpha_preserved':True,
 'optimizer':{'seeds':[14,29,73],'evaluations':sum(t.nfev for t in trials),'bounds':bounds},
 'reference_palette':[{'rgb':np.rint(rgb(c)*255).astype(int).tolist(),'weight':float(w)} for c,w in zip(r,rw)],
 'new_palette':[{'rgb':np.rint(rgb(c)*255).astype(int).tolist(),'weight':float(w)} for c,w in zip(s,sw)]}
args.output.write_text(json.dumps(report,indent=2)+'\n')
print('distance',before,after,'parameters',p,flush=True)
