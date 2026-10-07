"""Extra practice rotates only qualified cards and remembers civil-day cooldowns."""
import hashlib
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from yun_jin_data import Store
from yun_jin_study_rotation import PracticeHistory,source_key
from yun_jin_study_selection import select_pool,rotate_pool


class RotationTests(unittest.TestCase):
    def test_large_difficult_pool_has_variety_without_promoting_easy_cards(self):
        rows=[dict(id=i,note_id=i,deck_id=1,difficulty=i/1000,reps=100,lapses=0) for i in range(1,10001)]
        pool=select_pool(lambda:iter(rows));qualified={r['id'] for r in pool}
        self.assertEqual(qualified,set(range(9001,10001)))
        first=[r['id'] for r in rotate_pool(pool,'installation:day-one')[:36]]
        self.assertEqual(first,[r['id'] for r in rotate_pool(pool,'installation:day-one')[:36]])
        # First page samples the entire difficult decile instead of its first 36 ranks.
        self.assertLess(min(first),9200);self.assertGreater(max(first),9800)
        self.assertLess(len(set(first)&{r['id'] for r in rotate_pool(pool,'installation:day-two')[:36]}),10)
        seen=set(first);page=rotate_pool(pool,'installation:day-one',blocked=seen)[:36]
        self.assertFalse(seen&{r['id'] for r in page});self.assertTrue({r['id'] for r in page}<=qualified)
        self.assertEqual(rotate_pool(pool,'same',blocked=qualified),[])

    def test_cooldown_survives_restart_and_expires_after_yesterday(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);history=PracticeHistory(store)
            today=datetime.now().replace(hour=12,minute=0,second=0,microsecond=0)
            stamp=lambda days:(today-timedelta(days=days)).timestamp()
            history.record('native',[{'id':1,'note_id':100}],stamp(0))
            history.record('native',[{'id':2,'note_id':200}],stamp(1),reviewed=True)
            history.record('native',[{'id':3,'note_id':300}],stamp(2),reviewed=True)
            original=history.options('native',stamp(0));store.close()
            store=Store(tmp)
            try:
                reloaded=PracticeHistory(store);options=reloaded.options('native',stamp(0))
                self.assertEqual(options,original);self.assertEqual(set(options['cooldown_notes']),{100,200})
                self.assertEqual(options['visits']['300'],1)
                # Reverse cards share a note; revealing an offered card is not another visit.
                reloaded.record('native',[{'id':4,'note_id':100}],stamp(0)+1,reviewed=True)
                self.assertEqual(reloaded.options('native',stamp(0)+2)['visits']['100'],1)
                self.assertEqual(reloaded.options(source_key(Path(tmp)/'collection.anki2'),stamp(0))['cooldown_notes'],[])
                self.assertNotEqual(source_key(Path(tmp)/'one.anki2'),source_key(Path(tmp)/'two.anki2'))
            finally:store.close()

    def test_previous_release_history_migrates_once_without_changing_schedules(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            try:
                now=time.time();store.set_preference('study_prompt_history',dict(day=str(int(now)),notes=['a:42','n:43']))
                history=PracticeHistory(store,Path(tmp)/'collection.anki2')
                self.assertEqual(history.options('native',now)['cooldown_notes'],[43])
                self.assertEqual(history.options(source_key(Path(tmp)/'collection.anki2'),now)['cooldown_notes'],[42])
                self.assertIsNone(store.db.execute("SELECT name FROM sqlite_master WHERE name='sr_reviews'").fetchone())
                PracticeHistory(store,Path(tmp)/'collection.anki2')
                self.assertEqual(store.db.execute('SELECT sum(visits) FROM study_extra_history').fetchone()[0],2)
            finally:store.close()

    def test_anki_random_pages_stay_read_only_and_today_yesterday_are_excluded(self):
        from test_anki_reader import AnkiTests
        from yun_jin_anki import read_candidates
        fixture=AnkiTests();fixture.setUp()
        try:
            fixture.large_collection(count=6000)
            before=hashlib.sha256(fixture.path.read_bytes()).digest()
            a=read_candidates(fixture.path,fixture.now,rotation='day-a')
            ids={c['note_id'] for c in a['cards']}
            b=read_candidates(fixture.path,fixture.now,rotation='day-a',cooldown_notes=ids)
            self.assertEqual(a['total'],600);self.assertEqual(b['total'],600)
            self.assertEqual(len(a['cards']),36);self.assertFalse(ids&{c['note_id'] for c in b['cards']})
            self.assertLess(min(ids),5600)
            self.assertEqual(before,hashlib.sha256(fixture.path.read_bytes()).digest())
        finally:fixture.tearDown()


if __name__=='__main__':unittest.main(verbosity=2)
