# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only, bounded access to a user-selected local Anki collection.

Schema reference: ankitects/anki rslib/src/storage/card/data.rs and
proto/anki/notetypes.proto. No Anki code, plugin or scheduling writes are used.
Only decks actually studied today are eligible. No scheduling writes are made.
"""
from datetime import datetime, time as daytime, timedelta
from html.parser import HTMLParser
import html
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
from yun_jin_study_selection import select_pool

READ_SECONDS=8
SNAPSHOT_SECONDS=6


class CollectionBusy(RuntimeError):
    pass


def file_stamp(path):
    """Identity plus change detection, including WAL creation/removal/reset."""
    try:
        stat=path.stat()
        with path.open('rb') as stream:
            head=stream.read(128)
            stream.seek(max(0,stat.st_size-128));tail=stream.read(128)
        return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,head,tail)
    except FileNotFoundError:return None


def copy_bounded(source,destination,deadline):
    """Keep peak Python memory small; never change or checkpoint the source."""
    size=0
    with source.open('rb') as reader,destination.open('xb') as writer:
        while chunk:=reader.read(1024*1024):
            size+=len(chunk)
            if size>512*1024*1024 or time.monotonic()>deadline:
                raise CollectionBusy('La collezione richiede più tempo. Riprova con Anki chiuso.')
            writer.write(chunk)


def snapshot_collection(collection,folder,deadline):
    """Read a stable database/WAL pair when Anki holds its exclusive lock.

    Uncommitted WAL frames remain uncommitted in the private copy. Any observed
    write, checkpoint, rollback journal or file replacement aborts this attempt.
    SQLite then validates and reads only this disposable copy, never the source.
    """
    sources=[collection,Path(str(collection)+'-wal'),Path(str(collection)+'-journal')]
    for attempt in range(2):
        before=[file_stamp(path) for path in sources]
        if before[0] is None:raise FileNotFoundError(collection)
        # A hot rollback journal cannot be replayed safely from a live file copy.
        if before[2] and before[2][2]>0:
            raise CollectionBusy('Anki sta aggiornando la collezione. Riprova tra poco.')
        target=Path(folder)/str(attempt);target.mkdir()
        try:
            for path,stamp in zip(sources[:2],before[:2]):
                if stamp:
                    if stamp[2]>512*1024*1024:
                        raise CollectionBusy('Collezione molto grande. Riprova con Anki chiuso.')
                    copy_bounded(path,target/path.name,deadline)
            after=[file_stamp(path) for path in sources]
            if before==after:
                return target/collection.name
        except FileNotFoundError:pass  # Anki checkpointed/replaced the WAL mid-copy.
        if time.monotonic()>deadline:break
    raise CollectionBusy('Anki sta aggiornando la collezione. Riprova tra poco.')


def protobuf_fields(data):
    """Read the small public config fields we need; reject corrupt lengths."""
    result={}; position=0
    def varint():
        nonlocal position
        value=0
        for shift in range(0,70,7):
            if position>=len(data): raise ValueError('Configurazione Anki incompleta.')
            byte=data[position]; position+=1; value|=(byte&127)<<shift
            if byte<128: return value
        raise ValueError('Configurazione Anki non valida.')
    while position<len(data):
        tag=varint(); field,wire=tag>>3,tag&7
        if wire==0: value=varint()
        elif wire==2:
            size=varint()
            if size>len(data)-position: raise ValueError('Configurazione Anki incompleta.')
            value=data[position:position+size]; position+=size
        elif wire in (1,5):
            size=8 if wire==1 else 4; value=data[position:position+size];position+=size
        else: raise ValueError('Configurazione Anki non supportata.')
        result[field]=value
    return result


class PlainMedia(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts=[];self.media=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.hidden+=1
        if self.hidden: return
        if tag in ('br','div','p','hr','li'): self.parts.append('\n')
        if tag=='img':
            src=dict(attrs).get('src','')
            if src: self.media.append(src)
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.hidden: self.hidden-=1
        elif tag in ('div','p','li'): self.parts.append('\n')
    def handle_data(self,data):
        if not self.hidden: self.parts.append(data)


def simplify(value):
    parser=PlainMedia(); parser.feed(value)
    text=''.join(parser.parts)
    sounds=re.findall(r'\[sound:([^\]\r\n]+)\]',text)
    text=re.sub(r'\[sound:[^\]\r\n]+\]','',text)
    return re.sub(r'\n{3,}','\n\n',text).strip(), parser.media+sounds


def safe_media(root, name):
    from urllib.parse import unquote
    name=unquote(html.unescape(name))
    if not name or Path(name).name!=name or '/' in name or '\\' in name or ':' in name: return None
    path=root/name
    if path.suffix.lower() not in ('.png','.jpg','.jpeg','.gif','.webp','.mp3','.wav','.ogg','.m4a','.flac'): return None
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>32*1024*1024: return None
        return str(path.resolve())
    except OSError:
        return None


class StaticTemplate(HTMLParser):
    """Keep the static template, never execute or substitute inside scripts."""
    def __init__(self):
        super().__init__(convert_charrefs=False);self.parts=[];self.hidden=None
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden=tag
        if not self.hidden:self.parts.append(self.get_starttag_text())
    def handle_endtag(self,tag):
        if tag==self.hidden:self.hidden=None
        elif not self.hidden:self.parts.append('</'+tag+'>')
    def handle_startendtag(self,tag,attrs):
        if not self.hidden and tag not in ('script','style'):self.parts.append(self.get_starttag_text())
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)
    def handle_entityref(self,name):self.handle_data('&'+name+';')
    def handle_charref(self,name):self.handle_data('&#'+name+';')


def render_template(template, fields, ordinal, answer=False, front=''):
    from yun_jin_srs import CLOZE
    static=StaticTemplate();static.feed(template);static.close();template=''.join(static.parts)
    if re.search(r'<\s*(?:iframe|object)\b|\{\{(?:tts|type):',template,re.I):
        raise ValueError('Modello Anki avanzato non supportato.')
    for _ in range(8):
        updated=re.sub(r'\{\{([#^])([^{}]+)\}\}(.*?)\{\{/\2\}\}',
            lambda m:m[3] if bool(fields.get(m[2],''))==(m[1]=='#') else '',template,flags=re.S)
        if updated==template: break
        template=updated
    def replacement(match):
        expr=match[1]
        if expr=='FrontSide': return front
        pieces=expr.split(':'); key=pieces[-1]
        if key not in fields: raise ValueError('Campo del modello Anki non supportato.')
        value=fields[key]
        for modifier in reversed(pieces[:-1]):
            if modifier=='cloze':
                value=CLOZE.sub(lambda m: (m[2] if answer or int(m[1])!=ordinal+1 else '['+(m[3] or '…')+']'),value)
            elif modifier=='text': value=html.escape(simplify(value)[0])
            else: raise ValueError('Filtro del modello Anki non supportato.')
        return value
    return re.sub(r'\{\{([^{}]+)\}\}',replacement,template)


def anki_models(db, model_id, ordinal, legacy):
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'notetypes' in tables:
        row=db.execute('SELECT config FROM notetypes WHERE id=?',(model_id,)).fetchone()
        if row is None: raise ValueError('Modello Anki mancante.')
        is_cloze=protobuf_fields(row[0]).get(1,0)==1
        names=[r['name'] for r in db.execute('SELECT name FROM fields WHERE ntid=? ORDER BY ord',(model_id,))]
        template=db.execute('SELECT config FROM templates WHERE ntid=? AND ord=?',(model_id,0 if is_cloze else ordinal)).fetchone()
        if template is None: raise ValueError('Modello Anki mancante.')
        fields=protobuf_fields(template[0])
        return names, fields.get(1,b'').decode(), fields.get(2,b'').decode()
    model=legacy.get(str(model_id),{})
    template=model.get('tmpls',[])[0 if model.get('type')==1 else ordinal]
    return [f['name'] for f in model['flds']],template['qfmt'],template['afmt']


def study_window(db, now):
    rollover=4
    try:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'config' in tables:
            row=db.execute("SELECT val FROM config WHERE key='rollover'").fetchone()
            if row: rollover=int(json.loads(row[0]))
        else:
            row=db.execute('SELECT conf FROM col LIMIT 1').fetchone()
            if row: rollover=int(json.loads(row[0]).get('rollover',4))
    except (ValueError,TypeError,sqlite3.Error): pass
    rollover=max(0,min(23,rollover))
    day=(datetime.fromtimestamp(now)-timedelta(hours=rollover)).date()
    return (datetime.combine(day,daytime(rollover)).timestamp(),
            datetime.combine(day+timedelta(days=1),daytime(rollover)).timestamp())


def read_candidates(collection, now=None, limit=36, scratch=None, include_suspended=False,
                    exclude_notes=(), seen_day=None, restart=False,rotation=None,cooldown_notes=(),visits=None):
    now=time.time() if now is None else now
    limit=max(1,min(120,int(limit)))
    collection=Path(collection).expanduser().resolve(strict=True)
    if collection.name!='collection.anki2': raise ValueError('Seleziona collection.anki2 del tuo profilo Anki.')
    options=dict(include_suspended=include_suspended,exclude_notes=exclude_notes,seen_day=seen_day,restart=restart,
                 rotation=rotation,cooldown_notes=cooldown_notes,visits=visits)
    try:return _read_candidates(collection,collection,now,limit,**options)
    except sqlite3.OperationalError as exc:
        if getattr(exc,'sqlite_errorcode',0)&255 not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):raise
    with tempfile.TemporaryDirectory(prefix='yun-jin-anki-',dir=scratch) as folder:
        snapshot=snapshot_collection(collection,folder,time.monotonic()+SNAPSHOT_SECONDS)
        return _read_candidates(snapshot,collection,now,limit,validate=True,**options)


def anki_decks(db,tables,legacy):
    """Use Anki's own leech thresholds; tags belong to notes, lapses to cards."""
    decks={key:{**value,'threshold':8} for key,value in legacy.items()}
    if 'deck_config' in tables:
        configs={r['id']:protobuf_fields(r['config']).get(22,0) for r in db.execute('SELECT id,config FROM deck_config')}
    else:
        try:
            raw=db.execute('SELECT dconf FROM col LIMIT 1').fetchone()[0]
            configs={int(key):value.get('lapse',{}).get('leechFails',8) for key,value in json.loads(raw or '{}').items()}
        except sqlite3.OperationalError:configs={}
    if 'decks' in tables:
        columns={r['name'] for r in db.execute('PRAGMA table_info(decks)')}
        for row in db.execute('SELECT * FROM decks'):
            config_id=1
            if 'kind' in columns:
                normal=protobuf_fields(row['kind']).get(1,b'')
                if normal:config_id=protobuf_fields(normal).get(1,1)
            decks[str(row['id'])]=dict(name=row['name'].replace('\x1f','::'),threshold=configs.get(config_id,8))
    else:
        for value in decks.values():value['threshold']=configs.get(value.get('conf',1),8)
    return decks


def _read_candidates(database,collection,now,limit,validate=False,include_suspended=False,
                     exclude_notes=(),seen_day=None,restart=False,rotation=None,cooldown_notes=(),visits=None):
    deadline=time.monotonic()+READ_SECONDS
    timed_out=False
    def progress():
        nonlocal timed_out
        timed_out=time.monotonic()>deadline
        return int(timed_out)
    db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=.3)
    db.row_factory=sqlite3.Row
    try:
        # Modern Anki has WITHOUT ROWID tables and indexes using this collation.
        # SQLite needs it even for integer-key queries (otherwise: no query solution).
        # Our queries never use it to compare, filter or look up names.
        db.create_collation('unicase',lambda a,b:(a.casefold()>b.casefold())-(a.casefold()<b.casefold()))
        db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
        db.set_progress_handler(progress,10000)
        db.execute('BEGIN')
        if validate:
            # quick_check does not compare text through Anki's custom collation.
            if db.execute('PRAGMA quick_check(1)').fetchone()[0]!='ok':
                raise CollectionBusy('Anki sta aggiornando la collezione. Riprova tra poco.')
        start,end=study_window(db,now)
        legacy_row=db.execute('SELECT models,decks FROM col LIMIT 1').fetchone()
        legacy=json.loads(legacy_row['models'] or '{}');decks=json.loads(legacy_row['decks'] or '{}')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        decks=anki_decks(db,tables,decks)
        # ease=0/manual rescheduling does not make a deck "studied today".
        # Keep metadata only: large fields/media are loaded after selection.
        query='''WITH studied AS (
          SELECT DISTINCT CASE WHEN c.odid=0 THEN c.did ELSE c.odid END AS did
          FROM revlog r JOIN cards c ON c.id=r.cid
          WHERE r.id>=? AND r.id<? AND r.ease BETWEEN 1 AND 4 AND r.type BETWEEN 0 AND 3),
        recent AS (SELECT cid,count(*) AS recent_reviews,sum(ease=1) AS recent_failures,
          sum(ease=2) AS recent_hard,max(CASE WHEN ease=1 THEN id ELSE 0 END)/1000. AS last_failure
          FROM revlog WHERE id>=? AND id<? AND ease BETWEEN 1 AND 4 AND type=1 AND lastIvl>=1 GROUP BY cid),
        eligible AS (SELECT c.id,c.nid AS note_id,c.did AS deck_id,c.lapses,c.reps,c.factor/1000. AS ease,c.queue,n.tags,
          CASE WHEN json_valid(c.data) THEN json_extract(c.data,'$.d') END AS difficulty,
          coalesce((SELECT max(id) FROM revlog WHERE cid=c.id AND ease BETWEEN 1 AND 4 AND type BETWEEN 0 AND 3)/1000.,
            CASE WHEN json_valid(c.data) THEN json_extract(c.data,'$.lrt') END) AS last_review,
          coalesce(r.recent_reviews,0) AS recent_reviews,coalesce(r.recent_failures,0) AS recent_failures,
          coalesce(r.recent_hard,0) AS recent_hard,coalesce(r.last_failure,0) AS last_failure
          FROM cards c JOIN notes n ON n.id=c.nid JOIN studied s ON s.did=c.did LEFT JOIN recent r ON r.cid=c.id
          WHERE (c.queue>=0 OR (? AND c.queue=-1)) AND c.type IN (2,3) AND c.odid=0)
        SELECT * FROM eligible WHERE last_review<=?'''
        parameters=(int(start*1000),int((now+1)*1000),int((now-30*86400)*1000),int((now+1)*1000),
                    bool(include_suspended),now-1800)
        note_lapses={}
        def metadata():
            for record in db.execute(query,parameters):
                row=dict(record);threshold=decks.get(str(row['deck_id']),{}).get('threshold',8)
                tagged='leech' in row['tags'].casefold().split() and row['lapses']>0
                if tagged and row['note_id'] not in note_lapses:
                    note_lapses[row['note_id']]=db.execute('SELECT max(lapses) FROM cards WHERE nid=?',(row['note_id'],)).fetchone()[0]
                # A tag alone does not identify which direction caused it.
                # Respect the per-card threshold; a historical tag also keeps
                # the worst direction if that threshold has since changed.
                row['leech']=(bool(threshold and row['lapses']>=threshold) or
                              bool(tagged and row['lapses']>=note_lapses[row['note_id']]))
                if row['queue']<0 and not row['leech']:continue
                row['relative_eligible']=row['queue']>=0
                yield row
        pool=select_pool(metadata)
        total=len(pool);qualified=pool
        if rotation is not None:
            from yun_jin_study_selection import rotate_pool
            pool=rotate_pool(pool,rotation,visits,cooldown_notes)
        seen=set(exclude_notes) if seen_day is None or seen_day==start else set()
        selected=[row for row in pool if row['note_id'] not in seen]
        restarted=bool(restart and qualified and not selected)
        if restarted:
            # Explicit practice may repeat an exhausted pool; automatic prompts
            # always retain the today/yesterday exclusions in their controller.
            selected=rotate_pool(qualified,rotation,visits) if rotation is not None else qualified
        media_root=collection.parent/'collection.media';result=[];unsupported=0;issues=set();models={};payload_size=0
        skipped=[];consumed=0
        for row in selected:
            try:
                content=db.execute('SELECT c.ord,n.mid,n.flds FROM cards c JOIN notes n ON n.id=c.nid WHERE c.id=?',(row['id'],)).fetchone()
                if len(content['flds'])>200000:raise ValueError('Testo della carta troppo lungo.')
                key=(content['mid'],content['ord'])
                if key not in models:models[key]=anki_models(db,*key,legacy)
                names,qfmt,afmt=models[key]
                values=dict(zip(names,content['flds'].split('\x1f')))
                question=render_template(qfmt,values,content['ord'])
                answer=render_template(afmt,values,content['ord'],answer=True,front=question)
                front,fmedia=simplify(question);back,bmedia=simplify(answer)
                front_paths=[p for n in fmedia if (p:=safe_media(media_root,n))]
                back_paths=[p for n in bmedia if (p:=safe_media(media_root,n))]
                if not (front or front_paths) or not (back or back_paths):raise ValueError('Il modello non contiene un fronte e un retro leggibili senza script.')
                card=dict(id=row['id'],note_id=row['note_id'],deck=decks.get(str(row['deck_id']),{}).get('name','Anki'),
                    front=front,back=back,front_paths=front_paths[:12],back_paths=back_paths[:12],
                    difficulty=row['difficulty'],lapses=row['lapses'],leech=row['leech'],last_review=row['last_review'])
                size=len(json.dumps(card,ensure_ascii=True))
                if size>2*1024*1024:raise ValueError('Testo della carta troppo lungo.')
                if payload_size+size>2*1024*1024:break
                payload_size+=size;result.append(card);consumed+=1
                if len(result)>=limit: break
            except (ValueError,KeyError,IndexError,UnicodeError,TypeError,AttributeError) as exc:
                unsupported+=1;issues.add(str(exc)[:180]);skipped.append(row['note_id']);consumed+=1
        return dict(cards=result,total=total,more=consumed<len(selected),restarted=restarted,skipped=skipped,
            unsupported=unsupported,issues=sorted(issues)[:3],checked=now,study_start=start,study_end=end)
    except sqlite3.OperationalError as exc:
        if timed_out and getattr(exc,'sqlite_errorcode',0)&255==sqlite3.SQLITE_INTERRUPT:
            raise CollectionBusy('Lettura Anki troppo lenta. Riprova.') from exc
        raise
    finally:
        db.close()


def profile_root():
    if sys.platform=='darwin':return Path.home()/'Library/Application Support/Anki2'
    if sys.platform=='win32':return Path(os.environ.get('APPDATA',str(Path.home()/'AppData/Roaming')))/'Anki2'
    return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'Anki2'


def find_profiles():
    root=profile_root()
    try:return sorted(path for path in root.glob('*/collection.anki2') if path.is_file())
    except OSError:return []


if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.buffer.read(2*1024*1024))
        result=read_candidates(request['collection'],scratch=request.get('scratch'),
            include_suspended=bool(request.get('include_suspended',False)),exclude_notes=request.get('exclude_notes',()),
            seen_day=request.get('seen_day'),restart=bool(request.get('restart',False)),
            rotation=request.get('rotation'),cooldown_notes=request.get('cooldown_notes',()),visits=request.get('visits'))
    except FileNotFoundError:
        result=dict(cards=[],error='Collezione non trovata. Seleziona il profilo Anki.')
    except PermissionError:
        result=dict(cards=[],error='Accesso negato alla collezione Anki. Controlla i permessi della cartella.')
    except CollectionBusy as exc:
        result=dict(cards=[],error=str(exc),retry=True)
    except Exception as exc:
        result=dict(cards=[],error='Collezione Anki non leggibile.',detail=str(exc)[:250])
    # ASCII JSON survives Windows GUI launches with a non-UTF-8 stdout locale.
    print(json.dumps(result,ensure_ascii=True),flush=True)
