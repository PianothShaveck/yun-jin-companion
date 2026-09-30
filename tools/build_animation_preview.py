#!/usr/bin/env python3
"""Build a self-contained preview from render_animation_review.py's exact frames."""
import argparse
import json
from pathlib import Path

NAMES = ('morning16', 'afternoon16', 'evening16', 'greeting16', 'yawn16', 'sun16', 'cloud16',
         'rain16', 'snow16', 'applause16')

HTML = r'''<!doctype html>
<html lang="it">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yun Jin Companion · 1.2.1</title>
<style>
:root { color-scheme:light; font:16px/1.5 system-ui,sans-serif; color:#30263c; background:#f7f3fa }
* { box-sizing:border-box } body { margin:0; padding:32px 20px 24px }
main { max-width:960px; margin:auto } h1 { font-size:clamp(24px,4vw,34px); margin:0 0 20px; letter-spacing:-.025em }
h1 small { font-size:16px; font-weight:500; color:#7b648c; margin-left:8px }
button,select { font:inherit; color:inherit; background:#fff; border:1px solid #ded4e6; border-radius:10px; padding:8px 13px; cursor:pointer }
button:hover { border-color:#9a78b5 } button:focus-visible,select:focus-visible,input:focus-visible { outline:3px solid #af95c8; outline-offset:3px }
button[aria-pressed="true"] { color:white; background:#665079; border-color:#665079 }
nav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:22px }
.stages { display:grid; grid-template-columns:1fr 1fr; gap:18px }
figure { margin:0; border:1px solid #e3dbe8; border-radius:18px; overflow:hidden; background:#fff }
figcaption { padding:12px 18px; height:65px; display:flex; align-items:center; justify-content:space-between; gap:10px; font-weight:600 }
figcaption select { font-size:14px; padding:5px 7px; font-weight:400; max-width:190px }
.scene { height:340px; display:flex; align-items:flex-end; justify-content:center; padding:18px 0; background:radial-gradient(ellipse at 50% 100%,#e2d9eb,transparent 65%),#f0ecf4; overflow:hidden }
.scene img { display:block; height:279px; width:auto; object-fit:contain; flex-shrink:0 }
body.dark .scene { background:radial-gradient(ellipse at 50% 100%,#565062,transparent 65%),#34323b }
.controls { display:flex; align-items:center; gap:12px; margin-top:20px; flex-wrap:wrap }
.controls input[type=range] { flex:1; min-width:150px; accent-color:#705588 }
output { min-width:55px; text-align:center; font-variant-numeric:tabular-nums }
.options { margin-top:18px; display:flex; flex-wrap:wrap; align-items:center; gap:20px; color:#6c5a7a; font-size:14px }
.options label { display:flex; align-items:center; gap:8px } .options select { font-size:14px; padding:5px 8px }
.hint { margin:16px 0 0; font-size:14px; color:#6c5a7a; min-height:21px }
@media(max-width:600px) { body{padding:22px 12px} .stages{gap:10px} .scene{height:290px} .scene img{max-width:100%;height:auto;max-height:260px} figcaption{height:92px;display:flex;flex-direction:column;justify-content:center;gap:6px;padding:10px} figcaption select{max-width:140px;font-size:12px} h1 small{display:block;margin:0} }
</style>
<main>
<h1>Yun Jin Companion <small>Animazioni · 1.2.1</small></h1>
<nav aria-label="Animazione" id="clips"></nav>
<div class="stages">
  <figure><figcaption>Originale <select id="reference" aria-label="Animazione originale"><option value="still">Ferma</option></select></figcaption><div class="scene"><img id="original" alt="Yun Jin originale"></div></figure>
  <figure><figcaption id="clip-name"></figcaption><div class="scene"><img id="current" alt="Nuova animazione di Yun Jin"></div></figure>
</div>
<div class="controls">
  <button id="play" type="button">Pausa</button>
  <input id="frame" type="range" min="0" max="15" value="0" step="1" aria-label="Frame">
  <output id="counter" for="frame">1 / 16</output>
  <button id="next" type="button" aria-label="Frame successivo">Avanti</button>
</div>
<div class="options">
  <label>Dimensione <select id="scale"><option value="186">100%</option><option value="279" selected>150%</option><option value="310">167%</option></select></label>
  <label><input id="dark" type="checkbox"> Sfondo scuro</label>
</div>
<p class="hint" id="hint"></p>
</main>
<script type="application/json" id="animation-data">__DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.querySelector('#animation-data').textContent);
const $=s=>document.querySelector(s);
const current=$('#current'), original=$('#original');
let clip=data.clips.find(c=>c.name==='greeting16') || data.clips[0];
let frame=0, elapsed=0, refFrame=0, refElapsed=0, ref=null, playing=true, last=0;
const loaded=[];
for (const c of [...data.clips,...data.references]) for (const src of c.frames) {
  const img=new Image(); img.src=src; loaded.push(img);
}
const buttons=new Map();
for (const c of data.clips) {
  const b=document.createElement('button'); b.type='button'; b.textContent=c.label;
  b.onclick=()=>{clip=c;frame=0;elapsed=0;refFrame=0;refElapsed=0;draw();drawRef();};
  $('#clips').append(b); buttons.set(c.name,b);
}
for (const c of data.references) {
  const o=document.createElement('option');o.value=c.name;o.textContent=c.label.replace(' originale','');$('#reference').append(o);
}
function draw() {
  current.src=clip.frames[frame];$('#clip-name').textContent=clip.label;
  $('#frame').value=frame;$('#frame').max=clip.frames.length-1;
  $('#counter').textContent=`${frame+1} / ${clip.frames.length}`;
  $('#hint').textContent=clip.name==='applause16'?'Applauso: solo su comando.':'';
  for (const [name,b] of buttons) b.setAttribute('aria-pressed',String(name===clip.name));
}
function drawRef() { original.src=ref ? ref.frames[refFrame] : data.original; }
function setPlaying(value) {playing=value;last=0;$('#play').textContent=playing?'Pausa':'Riproduci';}
$('#play').onclick=()=>setPlaying(!playing);
$('#next').onclick=()=>{setPlaying(false);elapsed=0;frame=(frame+1)%clip.frames.length;draw();};
$('#frame').oninput=e=>{setPlaying(false);elapsed=0;frame=Number(e.target.value);draw();};
$('#reference').onchange=e=>{ref=data.references.find(c=>c.name===e.target.value)||null;refFrame=0;refElapsed=0;drawRef();};
$('#dark').onchange=e=>document.body.classList.toggle('dark',e.target.checked);
$('#scale').onchange=e=>{for(const img of [current,original])img.style.height=e.target.value+'px';};
document.addEventListener('visibilitychange',()=>{last=0;});
function tick(now) {
  const dt=last ? Math.min((now-last)/1000,.15) : 0;last=now;
  if (playing && !document.hidden) {
    elapsed+=dt;
    while (elapsed>=clip.timing[frame]) {elapsed-=clip.timing[frame];frame=(frame+1)%clip.frames.length;draw();}
    if(ref){refElapsed+=dt;while(refElapsed>=ref.timing[refFrame]){refElapsed-=ref.timing[refFrame];refFrame=(refFrame+1)%ref.frames.length;drawRef();}}
  }
  requestAnimationFrame(tick);
}
draw();drawRef();requestAnimationFrame(tick);
</script>
</html>
'''


def build(data_path, output):
    data = json.loads(Path(data_path).read_text(encoding='utf-8'))
    clips = {c['name']: c for c in data['clips']}
    data['clips'] = [clips[name] for name in NAMES]
    for clip in data['clips'] + data['references']:
        assert len(clip['frames']) == len(clip['timing'])
        assert all(t > 0 for t in clip['timing'])
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(HTML.replace('__DATA__', payload), encoding='utf-8')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('data', help='preview-data.json from render_animation_review.py')
    parser.add_argument('output', help='self-contained HTML file')
    args = parser.parse_args()
    build(args.data, args.output)
