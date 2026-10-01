"""SQLite/FSRS integration: real histories, limits, migration, media and recovery."""
import io,json,math,os,random,sqlite3,sys,tempfile,time,unittest,zipfile
from contextlib import closing,ExitStack
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from yun_jin_data import Store
from yun_jin_srs import *


class SrsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.s=self.store.study
        self.deck=self.s.save_deck('中文');self.now=datetime(2026,9,30,12,tzinfo=timezone.utc).timestamp()
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def add(self,kind='basic',content=None):
        nid=self.s.save_note(self.deck,kind,content or {'front':'你好','back':'Ciao'},now=self.now)
        return self.s.db.execute('SELECT id FROM sr_cards WHERE note_id=? ORDER BY ordinal',(nid,)).fetchone()[0]
    def answer(self,cid,rating,now=None,sid=None):
        if sid is None:sid=self.s.start_session(self.deck,now=self.now)
        return self.s.review(cid,rating,sid,now=self.now if now is None else now)

    def test_migration_preserves_existing_preferences_notes_and_reminders(self):
        self.store.save_note('Titolo','Testo');self.store.set_preference('volume',.73);self.store.add_reminder('Ciao',self.now+60)
        self.store.close();self.store=Store(self.tmp.name)
        self.assertEqual(self.store.notes()[0]['body'],'Testo');self.assertEqual(self.store.preference('volume',0),.73)
        self.assertEqual(self.store.reminders()[0]['title'],'Ciao');self.assertEqual(self.store.study.deck(self.deck)['name'],'中文')
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_default_learning_steps_and_fsrs_review_are_persisted(self):
        cid=self.add();sid=self.s.start_session(self.deck,now=self.now)
        for rating,elapsed,delay,state in [(1,0,10,1),(2,10,20,1),(3,30,30,1),(3,60,60,1),(3,120,600,1)]:
            _,after=self.answer(cid,rating,self.now+elapsed,sid)
            self.assertEqual(after['due']-(self.now+elapsed),delay);self.assertEqual(after['state'],state)
        _,after=self.answer(cid,3,self.now+720,sid);self.assertEqual(after['state'],2);self.assertGreaterEqual(after['due'],self.now+720+86400)
        self.assertEqual(self.s.card(cid)['reps'],6)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM sr_reviews WHERE card_id=?',(cid,)).fetchone()[0],6)
        self.assertEqual(self.s.deck(self.deck)['settings']['retention'],.9)
        self.assertIsNone(self.s.deck(self.deck)['settings']['new_limit'])

    def test_fsrs_matches_independent_rust_memory_trajectory(self):
        from fsrs_rs_python import FSRS,MemoryState,DEFAULT_PARAMETERS
        rust=FSRS(DEFAULT_PARAMETERS);memory=None;cid=self.add();now=self.now;previous=None
        for rating,days in [(3,0),(3,0),(1,0),(4,1),(2,8),(3,17),(1,38),(3,0),(4,6)]:
            now+=days*86400
            expected=getattr(rust.next_states(memory,.9,days),{1:'again',2:'hard',3:'good',4:'easy'}[rating]).memory
            _,actual=self.answer(cid,rating,now)
            self.assertAlmostEqual(actual['stability'],expected.stability,delta=max(.001,expected.stability*.00002))
            self.assertAlmostEqual(actual['difficulty'],expected.difficulty,places=4)
            memory=expected

    def test_relearning_and_ostinato_threshold_only_count_review_lapses(self):
        cid=self.add();_,after=self.answer(cid,4)
        for lapse in range(16):
            now=self.now+(lapse+1)*86400
            self.s.db.execute('UPDATE sr_cards SET state=2,suspended=0 WHERE id=?',(cid,));self.s.db.commit()
            _,after=self.answer(cid,1,now)
            self.assertEqual(after['due'],now+10);self.assertEqual(after['lapses'],lapse+1)
            self.assertEqual(after['suspended'],int(lapse==15))
        self.assertEqual(after['ostinato'],1)
        self.s.suspend(self.s.card(cid)['note_id'],False)
        _,after=self.answer(cid,1,now+10);self.assertEqual(after['lapses'],16)
        _,after=self.answer(cid,3,now+20);self.assertEqual(after['due'],now+50)

    def test_retention_and_empty_steps_change_interval_without_resetting_history(self):
        cid=self.add();settings=self.s.deck(self.deck)['settings'];settings.update(learning='',relearning='')
        self.s.save_deck('中文',settings,self.deck);row=self.s.card(cid)
        low=self.s.predict(row,4,self.now);settings['retention']=.97;self.s.save_deck('中文',settings,self.deck)
        high=self.s.predict(row,4,self.now);self.assertLess(high['due'],low['due']);self.assertEqual(high['state'],2)
        self.assertEqual(parse_steps('10s 0.5m 1 2h 1d'),
                         tuple(timedelta(seconds=n) for n in [10,30,60,7200,86400]))
        for value in ('x','0s','-2m','nan','1y'):
            with self.assertRaises(ValueError):parse_steps(value)

    def test_daily_limits_survive_restart_and_do_not_block_intraday_learning(self):
        a=self.add();b=self.add();settings=self.s.deck(self.deck)['settings'];settings.update(new_limit=1,review_limit=1)
        self.s.save_deck('中文',settings,self.deck);self.answer(a,1)
        self.assertIsNone(self.s.next_card(self.deck,now=self.now+1))
        self.assertEqual(self.s.next_card(self.deck,now=self.now+10)['id'],a)
        self.assertEqual(self.s.usage(self.deck,self.now)['new'],1)
        self.store.close();self.store=Store(self.tmp.name);self.s=self.store.study
        self.assertEqual(self.s.usage(self.deck,self.now)['new'],1)
        self.assertEqual(self.s.usage(self.deck,day_bounds(self.now)[1]+1)['new'],0)
        self.assertEqual(self.s.counts(self.deck,self.now)['new'],0)

    def test_cloze_edit_preserves_existing_schedules_and_deletes_removed_ordinals(self):
        cid=self.add('cloze',dict(front='{{c1::你好::saluto}}，{{c2::世界}}！',back=''))
        self.answer(cid,4);before=self.s.card(cid);note=before['note_id']
        self.s.save_note(self.deck,'cloze',dict(front='{{c1::你好}}，{{c3::中国}}！',back='Cina'),note,self.now+5)
        after=self.s.card(cid);self.assertEqual(after['stability'],before['stability']);self.assertEqual(after['due'],before['due'])
        self.assertGreater(after['revision'],before['revision'])
        active=self.s.db.execute('SELECT ordinal,state FROM sr_cards WHERE note_id=? AND deleted=0 ORDER BY ordinal',(note,)).fetchall()
        self.assertEqual([tuple(r) for r in active],[(1,2),(3,0)])
        self.assertIn('[saluto]',render_cloze('{{c1::你好::saluto}}',1));self.assertNotIn('<script>',render_cloze('{{c1::<script>}}',1,True))
        with self.assertRaises(ValueError):validate_content('cloze',{'front':'Senza lacune'})

    def test_undo_transaction_stale_revision_and_crash_recovery(self):
        cid=self.add();sid=self.s.start_session(self.deck);_,after=self.answer(cid,3,sid=sid)
        with self.assertRaises(ValueError):self.s.review(cid,4,sid,revision=0,now=self.now)
        self.assertEqual(self.s.undo(sid),cid);self.assertEqual(self.s.card(cid)['state'],0)
        self.assertEqual(self.s.usage(self.deck,self.now)['new'],0)
        self.answer(cid,4,sid=sid);self.store.close();self.store=Store(self.tmp.name);self.s=self.store.study
        self.assertEqual(self.s.card(cid)['reps'],1);self.assertEqual(self.s.card(cid)['state'],2)
        with self.assertRaises(ValueError):self.answer(cid,3,self.now-1,sid)
        self.assertEqual(self.s.card(cid)['reps'],1)

    def test_native_prompts_select_hard_due_cards_from_studied_decks(self):
        ids=[self.add() for _ in range(4)]
        for cid in ids:self.answer(cid,4,self.now-86400)
        self.s.db.execute('UPDATE sr_cards SET difficulty=8,lapses=16,ostinato=1,due=?',(self.now-10,));self.s.db.commit()
        self.assertEqual(self.s.hard_candidates(self.now),[])
        self.answer(ids[0],4,self.now)
        result=self.s.hard_candidates(self.now);self.assertEqual([r['id'] for r in result],ids[1:])
        self.s.suspend(self.s.card(ids[1])['note_id'],True)
        self.assertEqual([r['id'] for r in self.s.hard_candidates(self.now,exclude=[ids[2]])],[ids[3]])

    def test_native_relative_pool_finds_cards_below_the_old_threshold(self):
        ids=[self.add() for _ in range(20)]
        for index,cid in enumerate(ids):
            self.answer(cid,4,self.now-86400)
            self.s.db.execute('UPDATE sr_cards SET difficulty=?,lapses=0 WHERE id=?',(1+index/20,cid))
        # Study the easiest card today; all older reviews in that deck are eligible.
        self.answer(ids[0],4,self.now);self.s.db.commit()
        result=self.s.hard_candidates(self.now)
        self.assertEqual([r['id'] for r in result],ids[-1:-3:-1])
        self.assertEqual(self.s.hard_candidates(self.now,exclude=ids[-2:]),[])

    def test_media_is_owned_deduplicated_and_in_backup_with_schedules(self):
        path=Path(self.tmp.name)/'audio.wav';path.write_bytes(b'RIFF'+b'x'*200)
        media=self.s.import_media(path);self.assertEqual(self.s.import_media(path),media)
        cid=self.add(content=dict(front='你好',back='Ciao',front_media=[media]));self.answer(cid,4)
        path.unlink();self.assertTrue(self.s.media_path(media).is_file())
        backup=Path(self.tmp.name)/'backup.zip';self.store.export_backup(backup)
        with zipfile.ZipFile(backup) as archive:
            self.assertIn('study-media/'+media,archive.namelist());raw=archive.read('companion.sqlite3')
        snapshot=Path(self.tmp.name)/'snapshot.sqlite3';snapshot.write_bytes(raw)
        with closing(sqlite3.connect(snapshot)) as db:self.assertEqual(db.execute('SELECT reps FROM sr_cards WHERE id=?',(cid,)).fetchone()[0],1)
        with self.assertRaises(ValueError):self.s.media_path('../../other')

    def test_backup_closes_snapshot_and_cleans_up_on_success_and_failure(self):
        from unittest.mock import Mock,patch
        connect=sqlite3.connect;destination=self.store.root/'backup.zip'
        for failure in (None,'snapshot','archive'):
            with self.subTest(failure=failure):
                destination.write_bytes(b'previous backup');targets=[]
                def tracked_connect(*args,**kwargs):
                    target=connect(*args,**kwargs);targets.append(target)
                    self.addCleanup(target.close)
                    return target
                with ExitStack() as stack:
                    stack.enter_context(patch('yun_jin_data.sqlite3.connect',side_effect=tracked_connect))
                    if failure=='snapshot':
                        stack.enter_context(patch.object(self.store,'db',Mock(backup=Mock(side_effect=OSError('snapshot failed')))))
                    elif failure=='archive':
                        stack.enter_context(patch.object(zipfile.ZipFile,'write',side_effect=OSError('archive failed')))
                    if failure:
                        with self.assertRaisesRegex(OSError,failure+' failed'):
                            self.store.export_backup(destination)
                        self.assertEqual(destination.read_bytes(),b'previous backup')
                    else:
                        self.store.export_backup(destination)
                        self.assertTrue(zipfile.is_zipfile(destination))
                self.assertEqual(len(targets),1)
                for target in targets:
                    with self.assertRaises(sqlite3.ProgrammingError):target.execute('SELECT 1')
                self.assertEqual(list(self.store.root.glob('backup-*.sqlite3*')),[])
                self.assertFalse(destination.with_suffix('.zip.part').exists())

    def test_optimizer_keeps_defaults_with_insufficient_history(self):
        from yun_jin_srs_worker import optimize
        # Do not lower the test runner's priority or CPU limit.
        from unittest.mock import patch
        cid=self.add();self.answer(cid,3)
        with patch('yun_jin_srs_worker.low_priority'):
            result=optimize(self.store.root/'companion.sqlite3',self.deck)
        self.assertEqual(result['status'],'waiting');self.assertIsNone(self.s.deck(self.deck)['parameters'])

    def test_optimizer_trains_real_histories_and_validates_on_separate_cards(self):
        from yun_jin_srs_worker import optimize
        from unittest.mock import patch
        for index in range(30):
            cid=self.add()
            sid=self.s.start_session(self.deck)
            for review in range(8):
                rating=1 if (index+review)%3==0 else 3
                self.answer(cid,rating,self.now-(20-review)*86400,sid)
            self.s.end_session(sid)
        before=self.s.db.execute('SELECT sum(due) FROM sr_cards').fetchone()[0]
        with patch('yun_jin_srs_worker.low_priority'):
            result=optimize(self.store.root/'companion.sqlite3',self.deck)
        self.assertIn(result['status'],('optimized','kept'))
        self.assertGreaterEqual(result['samples'],100)
        if result['status']=='optimized':
            from fsrs import Scheduler
            Scheduler(parameters=result['parameters'])
            self.assertLess(result['new_loss'],result['old_loss'])
        self.assertEqual(self.s.db.execute('SELECT sum(due) FROM sr_cards').fetchone()[0],before)


class CandidateSelectionTests(unittest.TestCase):
    def rows(self,count=20,deck=1):
        return [dict(id=i,note_id=i,deck_id=deck,difficulty=1+i/20,lapses=0,reps=10,
                     leech=False,recent_reviews=0,recent_failures=0,recent_hard=0) for i in range(1,count+1)]

    def test_percentile_has_no_absolute_threshold_and_exclusions_do_not_expand_it(self):
        from yun_jin_study_selection import select_candidates
        rows=self.rows()
        self.assertEqual([r['id'] for r in select_candidates(rows)],[20,19])
        self.assertEqual(select_candidates(rows,exclude=[20,19]),[])
        self.assertEqual([r['id'] for r in select_candidates(rows[:1])],[1])

    def test_leech_pool_is_additional_and_recent_problems_take_priority(self):
        from yun_jin_study_selection import select_candidates
        rows=self.rows()
        rows[0].update(leech=True,lapses=20,reps=200)
        rows[1].update(leech=True,lapses=8,reps=40,recent_reviews=10,recent_failures=3,last_failure=100)
        picked=select_candidates(rows)
        self.assertEqual([r['id'] for r in picked],[2,20,1,19])

    def test_each_deck_gets_a_turn_and_reverse_cards_are_not_duplicated(self):
        from yun_jin_study_selection import select_candidates
        rows=self.rows()
        rows[-2]['note_id']=rows[-1]['note_id']
        other=self.rows(2,2)
        for row in other:row.update(id=row['id']+100,note_id=row['note_id']+100)
        self.assertEqual([r['id'] for r in select_candidates(rows+other)],[20,102])
        self.assertEqual([r['id'] for r in select_candidates(rows+other,exclude_notes=[20])],[102])

    def test_no_fsrs_uses_answers_and_long_streams_keep_a_bounded_pool(self):
        from yun_jin_study_selection import select_candidates
        rows=self.rows()
        for row in rows:row['difficulty']=None
        rows[4].update(recent_reviews=10,recent_failures=3)
        rows[8].update(recent_reviews=10,recent_hard=4)
        self.assertEqual([r['id'] for r in select_candidates(rows)],[5,9])
        def stream():
            for i in range(10000):yield dict(id=i,note_id=i,deck_id=1,difficulty=1+i/10000)
        self.assertEqual([r['id'] for r in select_candidates(stream(),3)],[9999,9998,9997])


if __name__=='__main__':unittest.main(verbosity=2)
