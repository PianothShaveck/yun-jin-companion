# SPDX-License-Identifier: GPL-3.0-or-later
"""Small, deterministic pools for optional practice, independent of scheduling."""
import heapq
import math
from itertools import zip_longest


def number(value, default=0.):
    try:
        result=float(value)
        return result if math.isfinite(result) else default
    except (TypeError,ValueError):return default


def priority(row, leech=False):
    # Recent *spaced* answers, not the 10s/30s learning steps. Four neutral
    # observations prevent one isolated failure dominating a longer history.
    count=number(row.get('recent_reviews'))+4
    failures=number(row.get('recent_failures'))/count
    hard=number(row.get('recent_hard'))/count
    difficulty=number(row.get('difficulty'))
    history=number(row.get('lapses'))/max(1,number(row.get('reps')))
    recent=number(row.get('last_failure'))
    fallback=-number(row.get('ease'),2.5)
    if leech:return failures,hard,recent,difficulty,history,-row['id']
    return difficulty,failures,hard,history,fallback,-row['id']


def select_pool(rows):
    """Complete pool from a repeatable metadata scan, without keeping the easy 90%.

    The caller holds one read transaction across both passes. Only counts are
    retained in the first pass; the second keeps the exact percentile and all
    leeches. Card text and media never enter either pass.
    """
    counts={}
    for row in rows():
        if row.get('relative_eligible',True):
            counts[row['deck_id']]=counts.get(row['deck_id'],0)+1
    return select_candidates(rows(),limit=None,deck_counts=counts)


def select_candidates(rows, limit=120, exclude=(), exclude_notes=(), *, deck_counts=None):
    """Union of leeches and the hardest 10% per eligible deck (rounded up).

    Only compact metadata enters this function. Small native requests keep a
    bounded heap; select_pool supplies exact deck counts for a complete pool.
    Never load card text or media to rank it.
    Exclusions are applied AFTER the percentile, so repeated calls do not
    gradually promote the easy 90%. Both groups and decks get a turn.
    """
    complete=limit is None and deck_counts is not None
    if not complete:
        limit=max(0,min(512,int(limit)))
        if not limit:return []
    cap=None if complete else max(120,limit);decks={}
    def keep(heap,key,row,size):
        if size==0:return
        value=(key,row)
        if size is None:heap.append(value)
        elif len(heap)<size:heapq.heappush(heap,value)
        elif key>heap[0][0]:heapq.heapreplace(heap,value)
    for record in rows:
        row=dict(record);deck=decks.setdefault(row['deck_id'],dict(count=0,hard=[],leech=[]))
        if row.get('relative_eligible',True):
            deck['count']+=1
            size=(deck_counts.get(row['deck_id'],0)+9)//10 if complete else cap
            keep(deck['hard'],priority(row),row,size)
        if row.get('leech'):keep(deck['leech'],priority(row,True),row,cap)
    def group(name):
        lanes=[]
        for deck in decks.values():
            size=(deck['count']+9)//10 if name=='hard' else cap
            if cap is not None and size is not None:size=min(cap,size)
            lane=[row for _,row in sorted(deck[name],key=lambda entry:entry[0],reverse=True)[:size]]
            if lane:lanes.append(lane)
        lanes.sort(key=lambda lane:priority(lane[0],name=='leech'),reverse=True)
        for batch in zip_longest(*lanes):
            yield from (row for row in batch if row is not None)
    seen=set(exclude);notes=set(exclude_notes);result=[]
    for pair in zip_longest(group('leech'),group('hard')):
        for row in pair:
            if row is None or row['id'] in seen or row['note_id'] in notes:continue
            seen.add(row['id']);notes.add(row['note_id']);result.append(row)
            if limit is not None and len(result)>=limit:return result
    return result
