# SPDX-License-Identifier: GPL-3.0-or-later
"""One cancellable network request per subprocess; JSON input/output, no shell."""
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

MAX_CHARS = 3000


def cache_key(job):
    spec={k:job.get(k) for k in ('provider','voice','language','rate','pitch','text')}
    return hashlib.sha256(json.dumps(spec,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()


def synthesize(job):
    text=str(job['text']).strip()
    if not text or len(text)>MAX_CHARS:
        raise ValueError('Scegli un testo da 1 a 3000 caratteri.')
    job=dict(job,text=text)
    root=Path(job['cache']).resolve()
    root.mkdir(parents=True,exist_ok=True)
    target=root/(cache_key(job)+'.mp3')
    if target.is_file() and target.stat().st_size>128:
        target.touch()
        return {'ok':True,'path':str(target),'cached':True}
    part=target.with_suffix('.part')
    try:
        if job['provider']=='edge':
            import edge_tts
            async def generate():
                speaker=edge_tts.Communicate(text,voice=job['voice'],
                    rate=f"{int(job.get('rate',0)):+d}%",pitch=f"{int(job.get('pitch',0)):+d}Hz",
                    connect_timeout=8,receive_timeout=20)
                await speaker.save(str(part))
            asyncio.run(asyncio.wait_for(generate(),timeout=38))
        elif job['provider']=='google':
            from gtts import gTTS
            gTTS(text=text,lang=job.get('language','it'),slow=int(job.get('rate',0))<0,
                 lang_check=False,timeout=(8,20)).save(str(part))
        else:
            raise ValueError('Servizio vocale non riconosciuto.')
        if not part.is_file() or part.stat().st_size<=128:
            raise ValueError('Il servizio non ha restituito audio valido.')
        os.replace(part,target)
        # Bound the cache to 100 MiB / 200 clips; the current result is kept.
        entries=sorted(root.glob('*.mp3'),key=lambda p:p.stat().st_mtime,reverse=True)
        total=0
        for index,path in enumerate(entries):
            total+=path.stat().st_size
            if path!=target and (index>=200 or total>100*1024*1024):
                try: path.unlink()
                except OSError: pass
        return {'ok':True,'path':str(target),'cached':False}
    finally:
        part.unlink(missing_ok=True)


def main():
    try:
        job=json.loads(sys.stdin.buffer.read().decode('utf-8'))
        result=synthesize(job)
    except ImportError as exc:
        result={'ok':False,'error':'Dipendenza TTS mancante: '+str(exc)+'. Esegui Installa-dipendenze-Windows.cmd.'}
    except Exception as exc:
        result={'ok':False,'error':type(exc).__name__+': '+str(exc)[:240]}
    sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
    sys.stdout.buffer.flush()


if __name__=='__main__':
    main()
