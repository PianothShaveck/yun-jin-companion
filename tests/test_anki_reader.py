"""Read real-shaped Anki SQLite schemas without writing any scheduling data."""
import hashlib,json,os,sqlite3,subprocess,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from unittest.mock import patch
from yun_jin_anki import read_candidates,safe_media,render_template,protobuf_fields,CollectionBusy,copy_bounded


def proto(**values):
    result=b''
    for field,value in values.items():
        raw=value.encode();n=len(raw);length=[]
        while n>127:length.append((n&127)|128);n>>=7
        length.append(n);result+=bytes([(int(field[1:])<<3)|2,*length])+raw
    return result


class AnkiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'collection.anki2';self.now=time.time()
        self.db=sqlite3.connect(self.path)
        self.db.executescript('''CREATE TABLE col(models text,decks text,conf text);
          CREATE TABLE notes(id integer primary key,mid integer,flds text,tags text NOT NULL DEFAULT '');
          CREATE TABLE cards(id integer primary key,nid integer,did integer,ord integer,type integer,queue integer,odid integer,lapses integer,factor integer,data text,reps integer NOT NULL DEFAULT 10);
          CREATE TABLE revlog(id integer primary key,cid integer,ease integer,type integer,lastIvl integer NOT NULL DEFAULT 1);
          CREATE INDEX idx_revlog_cid ON revlog(cid);
          CREATE TABLE config(key text primary key,val blob);''')
        model={'1':dict(type=0,flds=[dict(name='Front'),dict(name='Back')],tmpls=[dict(qfmt='{{Front}}',afmt='{{FrontSide}}<hr>{{Back}}')] )}
        self.db.execute('INSERT INTO col VALUES(?,?,?)',(json.dumps(model),json.dumps({'1':{'name':'中文'},'2':{'name':'Other'}}),'{}'))
        self.db.execute('INSERT INTO config VALUES(?,?)',('rollover',b'0'))
        for index in range(1,7):
            self.db.execute('INSERT INTO notes(id,mid,flds) VALUES(?,?,?)',(index,1,'你好\x1fCiao'))
            self.db.execute('INSERT INTO cards(id,nid,did,ord,type,queue,odid,lapses,factor,data) VALUES(?,?,?,0,2,2,0,3,1800,?)',
                            (index,index,2 if index==6 else 1,json.dumps({'s':3.2,'d':4 if index==2 else 8.7})))
        # Midnight time boundary may be close: choose a known local midday.
        from datetime import datetime
        local=datetime.now().replace(hour=12,minute=0,second=0,microsecond=0);self.now=local.timestamp()
        entries=[(1,self.now-3600,3),(2,self.now-86400,1),(3,self.now-3600,0),(4,self.now-30,1),(5,self.now-3600,2)]
        for index,(cid,timestamp,rating) in enumerate(entries):self.db.execute('INSERT INTO revlog(id,cid,ease,type) VALUES(?,?,?,1)',(int(timestamp*1000)+index,cid,rating))
        self.db.execute('UPDATE cards SET queue=-1 WHERE id=5');self.db.commit()
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def fingerprint(self):return hashlib.sha256(self.path.read_bytes()).digest()

    def test_relative_pool_respects_studied_decks_cooldown_and_suspensions(self):
        before=self.fingerprint();result=read_candidates(self.path,self.now)
        self.assertEqual([c['id'] for c in result['cards']],[1]);self.assertEqual(result['cards'][0]['front'],'你好')
        self.assertIn('Ciao',result['cards'][0]['back']);self.assertEqual(self.fingerprint(),before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM revlog').fetchone()[0],5)

    def test_modern_protobuf_templates_and_cloze(self):
        self.modern(cloze=True)
        self.db.execute('UPDATE notes SET flds=? WHERE id=1',('{{c1::你好::saluto}}！\x1fCiao',));self.db.commit()
        result=read_candidates(self.path,self.now)
        self.assertEqual(result['cards'][0]['front'],'[saluto]！');self.assertIn('你好',result['cards'][0]['back'])
        self.assertEqual(result['cards'][0]['deck'],'中文::词汇')

    def modern(self,cloze=False):
        # Anki 26.9.3 uses WITHOUT ROWID and unicase indexes. Plain rowid test
        # tables miss the "no query solution" failure in the real query planner.
        self.db.create_collation('unicase',lambda a,b:(a.casefold()>b.casefold())-(a.casefold()<b.casefold()))
        self.db.executescript('''CREATE TABLE notetypes(id integer primary key,config blob);
          CREATE TABLE fields(ntid integer not null,ord integer not null,name text not null collate unicase,
            config blob not null,primary key(ntid,ord)) without rowid;
          CREATE UNIQUE INDEX idx_fields_name_ntid ON fields(name,ntid);
          CREATE TABLE templates(ntid integer not null,ord integer not null,name text not null collate unicase,
            config blob not null,primary key(ntid,ord)) without rowid;
          CREATE UNIQUE INDEX idx_templates_name_ntid ON templates(name,ntid);
          CREATE TABLE decks(id integer primary key,name text not null collate unicase);
          CREATE UNIQUE INDEX idx_decks_name ON decks(name);
          UPDATE col SET models='',decks='';''')
        self.db.execute('INSERT INTO notetypes VALUES(1,?)',(b'\x08\x01' if cloze else b'',))
        self.db.executemany('INSERT INTO fields VALUES(1,?,?,?)',[(0,'Front',b''),(1,'Back',b'')])
        question='{{cloze:Front}}' if cloze else '{{Front}}'
        self.db.execute('INSERT INTO templates VALUES(1,0,?,?)',('Carta',proto(f1=question,f2=question+'<br>{{Back}}')))
        self.db.execute('INSERT INTO decks VALUES(1,?)',('中文\x1f词汇',));self.db.commit()

    def test_modern_indexed_schema_reads_directly_and_with_exclusive_wal(self):
        self.modern()
        before=self.fingerprint();direct=read_candidates(self.path,self.now)
        self.assertEqual(direct['cards'][0]['front'],'你好');self.assertEqual(self.fingerprint(),before)
        self.exclusive();wal=Path(str(self.path)+'-wal');before=(self.path.read_bytes(),wal.read_bytes())
        snapshot=read_candidates(self.path,self.now)
        self.assertEqual(snapshot['cards'][0]['front'],'学习')
        self.assertEqual((self.path.read_bytes(),wal.read_bytes()),before)

    def test_profiles_are_found_in_standard_mac_location(self):
        from yun_jin_anki import find_profiles,profile_root
        home=Path(self.tmp.name);root=home/'Library/Application Support/Anki2'
        profile=root/'Utente 1';profile.mkdir(parents=True);collection=profile/'collection.anki2';collection.touch()
        with patch('yun_jin_anki.sys.platform','darwin'),patch('yun_jin_anki.Path.home',return_value=home):
            self.assertEqual(profile_root(),root);self.assertEqual(find_profiles(),[collection])

    def test_static_content_survives_decorative_scripts_without_running_them(self):
        model=json.loads(self.db.execute('SELECT models FROM col').fetchone()[0]);model['1']['tmpls'][0]['qfmt']='<script>alert(1)</script>{{Front}}'
        self.db.execute('UPDATE col SET models=?',(json.dumps(model),));self.db.commit()
        result=read_candidates(self.path,self.now);self.assertEqual(result['cards'][0]['front'],'你好');self.assertEqual(result['unsupported'],0)
        self.assertNotIn('alert',result['cards'][0]['back'])

    def test_script_only_content_is_reported_and_template_variables_inside_scripts_are_ignored(self):
        rendered=render_template('{{Front}}<script>const text="{{Unknown}}";</script>',{'Front':'你好'},0)
        self.assertEqual(rendered,'你好')
        model=json.loads(self.db.execute('SELECT models FROM col').fetchone()[0])
        model['1']['tmpls'][0]['qfmt']='<script>document.write("{{Front}}")</script>'
        self.db.execute('UPDATE col SET models=?',(json.dumps(model),));self.db.commit()
        result=read_candidates(self.path,self.now)
        self.assertEqual(result['cards'],[]);self.assertEqual(result['unsupported'],1)
        self.assertIn('senza script',result['issues'][0])

    def test_deck_studied_today_allows_an_older_hard_card_without_an_absolute_threshold(self):
        self.db.execute('UPDATE cards SET data=? WHERE id=1',(json.dumps({'d':1.2,'s':300}),))
        self.db.execute('UPDATE cards SET data=? WHERE id=2',(json.dumps({'d':2.3,'s':200}),));self.db.commit()
        result=read_candidates(self.path,self.now)
        self.assertEqual([c['id'] for c in result['cards']],[2])
        self.assertLess(result['cards'][0]['last_review'],self.now-86400+1)
        self.db.execute('DELETE FROM revlog WHERE id>=?',(int((self.now-12*3600)*1000),));self.db.commit()
        self.assertEqual(read_candidates(self.path,self.now)['cards'],[])

    def test_leech_tag_does_not_promote_the_easy_reverse_and_suspensions_are_optional(self):
        self.db.execute('UPDATE notes SET tags=" leech " WHERE id=2')
        self.db.execute('UPDATE cards SET lapses=9,queue=-1 WHERE id=2')
        self.db.execute('UPDATE cards SET nid=2,lapses=1,data=? WHERE id=3',(json.dumps({'d':1.1}),))
        self.db.execute('INSERT INTO revlog(id,cid,ease,type) VALUES(?,?,3,1)',(int((self.now-2*86400)*1000),3));self.db.commit()
        before=self.fingerprint()
        self.assertEqual([r['id'] for r in read_candidates(self.path,self.now)['cards']],[1])
        result=read_candidates(self.path,self.now,include_suspended=True)
        self.assertIn(2,[r['id'] for r in result['cards']]);self.assertNotIn(3,[r['id'] for r in result['cards']])
        self.assertNotIn(5,[r['id'] for r in result['cards']])  # Unrelated suspension.
        self.assertEqual(before,self.fingerprint());self.assertEqual(self.db.execute('SELECT queue FROM cards WHERE id=2').fetchone()[0],-1)

    def test_anki_configured_leech_threshold_is_used_without_a_tag(self):
        self.modern()
        self.db.execute("CREATE TABLE deck_config(id integer primary key,config blob)")
        # DeckConfig.Config.leech_threshold: field 22, varint 5.
        self.db.execute('INSERT INTO deck_config VALUES(1,?)',(b'\xb0\x01\x05',))
        self.db.execute('UPDATE cards SET lapses=5 WHERE id=2');self.db.commit()
        result=read_candidates(self.path,self.now)
        self.assertTrue(next(row for row in result['cards'] if row['id']==2)['leech'])

    def test_recent_learning_steps_do_not_count_as_spaced_failures(self):
        self.db.execute('UPDATE cards SET data=? WHERE id=2',(json.dumps({'d':8.7}),))
        self.db.execute('UPDATE revlog SET ease=3 WHERE cid=2')
        for i in range(20):
            self.db.execute('INSERT INTO revlog(id,cid,ease,type,lastIvl) VALUES(?,?,1,2,-30)',(int((self.now-3600)*1000)+i+100,2))
        self.db.commit();self.assertEqual(read_candidates(self.path,self.now)['cards'][0]['id'],1)

    def test_model_media_stays_on_the_correct_side_in_both_directions(self):
        media=self.path.parent/'collection.media';media.mkdir();(media/'test.png').write_bytes(b'local-image')
        fields={'Fronte':'Square face','Retro':'方圆脸<img src="test.png">'}
        from yun_jin_anki import simplify
        for first,second in [('Fronte','Retro'),('Retro','Fronte')]:
            q=render_template('{{'+first+'}}<script>/* formatting */</script>',fields,0)
            a=render_template('{{FrontSide}}<hr>{{'+second+'}}',fields,0,True,q)
            self.assertEqual(simplify(q)[1],['test.png'] if first=='Retro' else [])
            self.assertEqual(simplify(a)[1],['test.png'])

    def test_media_cannot_escape_anki_media_folder(self):
        root=Path(self.tmp.name)/'collection.media';root.mkdir();(root/'voice.mp3').write_bytes(b'audio')
        self.assertEqual(safe_media(root,'voice.mp3'),str((root/'voice.mp3').resolve()))
        for name in ('../collection.anki2','%2e%2e/secret.png','https://example.com/a.png','file:/etc/passwd','a\\b.mp3'):
            self.assertIsNone(safe_media(root,name))
        with self.assertRaises(ValueError):protobuf_fields(b'\x0a\xff\xff')

    def test_read_only_wal_sees_committed_reviews_while_anki_is_open(self):
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('UPDATE notes SET flds=? WHERE id=1',('学习\x1fStudiare',));self.db.commit()
        before_cards=self.db.execute('SELECT * FROM cards').fetchall();before_revlog=self.db.execute('SELECT * FROM revlog').fetchall()
        result=read_candidates(self.path,self.now);self.assertEqual(result['cards'][0]['front'],'学习')
        self.assertEqual(before_cards,self.db.execute('SELECT * FROM cards').fetchall())
        self.assertEqual(before_revlog,self.db.execute('SELECT * FROM revlog').fetchall())

    def exclusive(self):
        # Same locking/journal modes as Anki's open_or_create_collection_db().
        self.db.execute('PRAGMA locking_mode=exclusive');self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('UPDATE notes SET flds=? WHERE id=1',('学习\x1fStudiare',));self.db.commit()

    def test_real_anki_exclusive_lock_reads_committed_wal_and_preserves_original(self):
        self.exclusive();wal=Path(str(self.path)+'-wal')
        before=(self.path.read_bytes(),wal.read_bytes())
        media=self.path.parent/'collection.media';media.mkdir();(media/'voce.mp3').write_bytes(b'audio')
        self.db.execute('UPDATE notes SET flds=? WHERE id=1',('学习[sound:voce.mp3]\x1fStudiare',));self.db.commit()
        before=(self.path.read_bytes(),wal.read_bytes())
        with tempfile.TemporaryDirectory() as scratch:
            result=read_candidates(self.path,self.now,scratch=scratch)
            self.assertFalse(list(Path(scratch).iterdir()))
        self.assertEqual(result['cards'][0]['front'],'学习')
        self.assertEqual(result['cards'][0]['front_paths'],[str((media/'voce.mp3').resolve())])
        self.assertEqual((self.path.read_bytes(),wal.read_bytes()),before)

    def test_uncommitted_anki_changes_never_appear_in_snapshot(self):
        self.exclusive();self.db.execute('UPDATE notes SET flds=? WHERE id=1',('Non ancora salvato\x1fNascosto',))
        try:self.assertEqual(read_candidates(self.path,self.now)['cards'][0]['front'],'学习')
        finally:self.db.rollback()

    def test_concurrent_anki_writes_are_retried_or_rejected(self):
        self.exclusive();changes=[]
        # read_candidates resolves aliases before copying. Exercise that on
        # every platform, rather than depending on the runner's temp location.
        alias=self.path.parent/'alias';alias.mkdir()
        self.path=alias/'..'/self.path.name
        source_path=self.path.resolve()
        def changing_copy(source,destination,deadline):
            copy_bounded(source,destination,deadline)
            if source==source_path:
                changes.append(1)
                self.db.execute('UPDATE notes SET flds=? WHERE id=1',(f'変更{len(changes)}\x1fNuovo',));self.db.commit()
        with patch('yun_jin_anki.copy_bounded',side_effect=changing_copy):
            with self.assertRaises(CollectionBusy):read_candidates(self.path,self.now)
        self.assertEqual(len(changes),2)
        self.assertEqual(read_candidates(self.path,self.now)['cards'][0]['front'],'変更2')

    def test_worker_protocol_handles_chinese_even_with_ascii_console(self):
        from datetime import datetime
        self.db.execute('UPDATE config SET val=? WHERE key=?',(str((datetime.now().hour+1)%24),'rollover'))
        self.db.execute('DELETE FROM revlog');self.db.execute('INSERT INTO revlog(id,cid,ease,type) VALUES(?,?,3,1)',(int((time.time()-3600)*1000),1));self.db.commit()
        self.exclusive()
        script=Path(__file__).resolve().parents[1]/'app/yun_jin_anki.py'
        result=subprocess.run([sys.executable,str(script)],input=json.dumps({'collection':str(self.path)}).encode(),
            capture_output=True,timeout=10,env={**os.environ,'PYTHONIOENCODING':'ascii'})
        self.assertEqual(result.returncode,0,result.stderr)
        document=json.loads(result.stdout);self.assertNotIn('error',document)
        self.assertEqual(document['cards'][0]['front'],'学习')

    def large_collection(self,count=5200,suspended=0):
        self.db.executescript('DELETE FROM cards; DELETE FROM notes; DELETE FROM revlog;')
        self.db.executemany('INSERT INTO notes(id,mid,flds,tags) VALUES(?,1,?,?)',
            ((i,f'词语 {i}\x1fRisposta {i}',' leech ' if i>count else '') for i in range(1,count+suspended+1)))
        self.db.executemany('INSERT INTO cards(id,nid,did,ord,type,queue,odid,lapses,factor,data) VALUES(?,?,1,0,2,?,0,?,2500,?)',
            ((i,i,-1 if i>count else 2,9 if i>count else 0,
              json.dumps(dict(d=1+i/count*9 if i<=count else 2,lrt=self.now-86400)))
             for i in range(1,count+suspended+1)))
        self.db.execute('INSERT INTO revlog(id,cid,ease,type) VALUES(?,1,3,1)',(int((self.now-3600)*1000),))
        self.db.commit()

    def test_total_and_rotation_cover_all_520_candidates_without_loading_all_text(self):
        self.large_collection();before=self.fingerprint();seen=[];ids=[];calls=[]
        from yun_jin_anki import render_template as render
        with patch('yun_jin_anki.render_template',wraps=render) as rendered:
            first=read_candidates(self.path,self.now)
            self.assertEqual(first['total'],520);self.assertEqual(len(first['cards']),36)
            self.assertEqual(rendered.call_count,72);self.assertTrue(first['more'])
        page=first
        while page['cards']:
            self.assertEqual(page['total'],520)
            current=[c['note_id'] for c in page['cards']]
            self.assertFalse(set(current)&set(seen));seen.extend(current)
            ids.extend(c['id'] for c in page['cards']);calls.append(len(current))
            page=read_candidates(self.path,self.now,exclude_notes=seen,seen_day=first['study_start'])
        self.assertEqual(set(ids),set(range(4681,5201)));self.assertGreater(len(calls),12)
        self.assertFalse(page['more']);self.assertEqual(page['total'],520)
        restarted=read_candidates(self.path,self.now,exclude_notes=seen,restart=True)
        self.assertTrue(restarted['restarted']);self.assertEqual(restarted['cards'],first['cards'])
        self.assertEqual(self.fingerprint(),before)

    def test_suspended_leeches_increase_total_without_replacing_active_percentile(self):
        self.large_collection(suspended=60);before=self.fingerprint()
        active=read_candidates(self.path,self.now);mixed=read_candidates(self.path,self.now,include_suspended=True)
        self.assertEqual((active['total'],mixed['total']),(520,580))
        self.assertEqual(len(mixed['cards']),36)
        self.assertTrue(any(card['id']>5200 for card in mixed['cards']))
        self.assertTrue(any(card['id']<=5200 for card in mixed['cards']))
        # Exhaust the ordinary cards: all sixty extra cards remain reachable.
        extra=read_candidates(self.path,self.now,limit=120,include_suspended=True,exclude_notes=range(4681,5201))
        self.assertEqual({card['id'] for card in extra['cards']},set(range(5201,5261)))
        self.assertEqual(extra['total'],580);self.assertEqual(self.fingerprint(),before)

    def test_new_study_day_discards_old_page_exclusions(self):
        first=read_candidates(self.path,self.now)
        page=read_candidates(self.path,self.now,exclude_notes=[1],seen_day=first['study_start']-86400)
        self.assertEqual(page['cards'],first['cards']);self.assertFalse(page['restarted'])

    def test_payload_limit_leaves_the_next_card_for_the_next_page(self):
        self.large_collection(count=30)
        # Escaped Chinese consumes six JSON bytes per character, on both sides.
        self.db.execute('UPDATE notes SET flds=?',('词'*170000+'\x1fA',));self.db.commit()
        first=read_candidates(self.path,self.now)
        self.assertEqual(first['total'],3);self.assertEqual(len(first['cards']),1);self.assertTrue(first['more'])
        second=read_candidates(self.path,self.now,exclude_notes=[first['cards'][0]['note_id']])
        self.assertEqual(len(second['cards']),1);self.assertNotEqual(first['cards'][0]['id'],second['cards'][0]['id'])


if __name__=='__main__':unittest.main(verbosity=2)
