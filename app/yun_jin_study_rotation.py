# SPDX-License-Identifier: GPL-3.0-or-later
"""Local history for extra practice. Never writes to an Anki collection."""
from datetime import datetime,timedelta,time as day_time
import hashlib
import os
from pathlib import Path
import secrets
import time


def source_key(path=''):
    if not path:return 'native'
    return 'anki:'+hashlib.sha256(os.path.normcase(str(Path(path).expanduser().resolve())).encode()).hexdigest()[:24]


class PracticeHistory:
    def __init__(self,store,anki_path=''):
        self.store=store;self.db=store.db
        self.db.execute('''CREATE TABLE IF NOT EXISTS study_extra_history(
          source TEXT NOT NULL,note_id INTEGER NOT NULL,last_seen REAL NOT NULL,
          visits INTEGER NOT NULL,last_reviewed REAL,PRIMARY KEY(source,note_id))''')
        self.db.execute('CREATE INDEX IF NOT EXISTS study_extra_last_seen ON study_extra_history(last_seen)')
        self.db.commit()
        self.seed=store.preference('study_rotation_seed','')
        if not self.seed:
            self.seed=secrets.token_hex(16);store.set_preference('study_rotation_seed',self.seed)
        if not store.preference('study_rotation_migrated',False):
            old=store.preference('study_prompt_history',{})
            try:
                stamp=float(old.get('day',0))
                for key in old.get('notes',[]):
                    if isinstance(key,str) and key[:2] in ('a:','n:') and key[2:].isdigit():
                        self.record(source_key(anki_path) if key.startswith('a:') else 'native',
                                    [{'note_id':int(key[2:])}],stamp)
            except (ValueError,TypeError,AttributeError):pass
            store.set_preference('study_rotation_migrated',True)
        with self.db:self.db.execute('DELETE FROM study_extra_history WHERE last_seen<?',(time.time()-60*86400,))

    def options(self,source,now=None):
        now=time.time() if now is None else now
        today=datetime.fromtimestamp(now).date()
        # Calendar days, including 23/25-hour days at daylight-saving changes.
        yesterday=datetime.combine(today-timedelta(days=1),day_time()).timestamp()
        rows=self.db.execute('SELECT note_id,last_seen,visits FROM study_extra_history WHERE source=? AND last_seen>=?',
                             (source,now-60*86400))
        blocked=[];visits={}
        for row in rows:
            visits[str(row['note_id'])]=row['visits']
            if row['last_seen']>=yesterday:blocked.append(row['note_id'])
        return dict(rotation=self.seed+':'+source+':'+today.isoformat(),cooldown_notes=blocked,visits=visits)

    def record(self,source,cards,now=None,reviewed=False):
        now=time.time() if now is None else now
        today=datetime.combine(datetime.fromtimestamp(now).date(),day_time()).timestamp()
        notes={int(c.get('note_id',c.get('id'))) for c in cards}
        with self.db:
            self.db.executemany('''INSERT INTO study_extra_history VALUES(?,?,?,1,?)
              ON CONFLICT(source,note_id) DO UPDATE SET
              visits=study_extra_history.visits+(study_extra_history.last_seen<?),
              last_seen=max(study_extra_history.last_seen,excluded.last_seen),
              last_reviewed=coalesce(excluded.last_reviewed,study_extra_history.last_reviewed)''',
              ((source,note,now,now if reviewed else None,today) for note in notes))
