# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, low-priority FSRS optimization; isolated from the Qt process.

The official Rust optimizer uses hand-coded gradients, no Torch/NumPy. A session
requests a fit; insufficient evidence or worse held-out loss keeps the old model.
"""
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time


def low_priority():
    for key in ('RAYON_NUM_THREADS','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        os.environ[key]='1'
    try:
        if sys.platform=='win32':
            import ctypes
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.GetCurrentProcess.restype=ctypes.c_void_p
            kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
            kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x00004000)
        else:
            os.nice(10)
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(10,12))
    except (OSError,ImportError,ValueError): pass


def optimize(database, deck_id):
    low_priority()
    db=sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=1)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        deck=db.execute('SELECT * FROM sr_decks WHERE id=? AND archived=0',(deck_id,)).fetchone()
        if not deck or not json.loads(deck['settings']).get('fsrs',True): return {'status':'disabled'}
        through=db.execute('SELECT coalesce(max(id),0) FROM sr_reviews WHERE deck_id=? AND undone=0',(deck_id,)).fetchone()[0]
        base=dict(deck_id=deck_id,through=through,generation=deck['generation'])
        if through<=deck['optimized_through']: return {**base,'status':'unchanged'}
        card_ids=[r[0] for r in db.execute('''SELECT card_id FROM sr_reviews WHERE deck_id=? AND undone=0
          GROUP BY card_id HAVING count(*) BETWEEN 2 AND 256 ORDER BY max(id) DESC LIMIT 400''',(deck_id,))]
        histories=[]; elapsed_targets=0
        for card_id in card_ids:
            rows=db.execute('''SELECT rating,reviewed,state_before FROM sr_reviews
               WHERE card_id=? AND undone=0 ORDER BY id''',(card_id,)).fetchall()
            # Never reconstruct a history from its middle (e.g. future imports).
            if not rows or rows[0]['state_before']!=0: continue
            history=[]; previous=None
            for row in rows:
                delta=0 if previous is None else max(0,int((row['reviewed']-previous)//86400))
                history.append((row['rating'],delta)); previous=row['reviewed']
                if delta>0: elapsed_targets+=1
            histories.append((card_id,history))
        db.rollback()
    finally: db.close()
    if elapsed_targets<100 or len(histories)<20:
        return {**base,'status':'waiting','samples':elapsed_targets}
    from fsrs_rs_python import FSRS, FSRSItem, FSRSReview, TrainingConfig, DEFAULT_PARAMETERS
    from fsrs import Scheduler
    current=json.loads(deck['parameters']) if deck['parameters'] else DEFAULT_PARAMETERS
    train,valid,ids=[],[],[]
    for index,(card_id,history) in enumerate(histories):
        reviews=[FSRSReview(rating,delta) for rating,delta in history]
        targets=[i for i,(_,delta) in enumerate(history) if i>0 and delta>0][-16:]
        for i in targets:
            item=FSRSItem(reviews[:i+1])
            if index%5==0: valid.append(item)
            else: train.append(item); ids.append(card_id)
    if len(train)<80 or len(valid)<20: return {**base,'status':'waiting','samples':len(train)+len(valid)}
    old_loss=FSRS(current).evaluate(valid).log_loss
    parameters=FSRS(current).compute_parameters(train,card_ids=ids,enable_short_term=True,
        num_relearning_steps=len(str(json.loads(deck['settings']).get('relearning','')).split()),
        training_config=TrainingConfig(num_epochs=5,batch_size=256,max_seq_len=256))
    # Validate the exact scheduler we will use before committing anything.
    Scheduler(parameters=parameters)
    new_loss=FSRS(parameters).evaluate(valid).log_loss
    result={**base,'samples':len(train)+len(valid),'old_loss':old_loss,'new_loss':new_loss}
    if not math.isfinite(new_loss) or new_loss>=old_loss-1e-5:
        return {**result,'status':'kept'}
    return {**result,'status':'optimized','parameters':parameters}


def main():
    try:
        request=json.loads(sys.stdin.buffer.read(16384))
        result=optimize(request['database'],int(request['deck_id']))
    except Exception as exc:
        result={'status':'failed','detail':str(exc)[:300]}
    print(json.dumps(result,allow_nan=False),flush=True)

if __name__=='__main__': main()
