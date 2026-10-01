# SPDX-License-Identifier: GPL-3.0-or-later
"""Native, transactional flashcards. No Qt, Anki process or network dependency.

Content is versioned independently of scheduling, so future card types can share
notes, media and review history. FSRS is loaded only when it is actually needed.
"""
from datetime import datetime, time as daytime, timedelta, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

DEFAULTS = dict(retention=.90, new_limit=None, review_limit=None,
                learning='10s 30s 1m 10m', relearning='10s 30s 1m',
                leech_threshold=16, suspend_leeches=True, fsrs=True)
DAY_START = 4
CLOZE = re.compile(r'\{\{c([1-9][0-9]?)::(.*?)(?:::(.*?))?\}\}', re.S)
MEDIA = re.compile(r'^[0-9a-f]{64}\.(?:png|jpg|jpeg|gif|webp|wav|mp3|ogg|m4a|flac)$')
MEDIA_TYPES = {'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','gif':'image/gif',
               'webp':'image/webp','wav':'audio/wav','mp3':'audio/mpeg','ogg':'audio/ogg',
               'm4a':'audio/mp4','flac':'audio/flac'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS sr_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO sr_meta VALUES('schema','1');
CREATE TABLE IF NOT EXISTS sr_decks(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
 settings TEXT NOT NULL, parameters TEXT, generation INTEGER NOT NULL DEFAULT 0,
 optimized REAL, optimizer_status TEXT NOT NULL DEFAULT 'waiting',
 optimized_through INTEGER NOT NULL DEFAULT 0, archived INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sr_notes(
 id INTEGER PRIMARY KEY, deck_id INTEGER NOT NULL REFERENCES sr_decks(id),
 kind TEXT NOT NULL, content TEXT NOT NULL, content_version INTEGER NOT NULL DEFAULT 1,
 created REAL NOT NULL, modified REAL NOT NULL, deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sr_cards(
 id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES sr_notes(id),
 ordinal INTEGER NOT NULL, state INTEGER NOT NULL DEFAULT 0, step INTEGER,
 stability REAL, difficulty REAL, due REAL NOT NULL, last_review REAL,
 reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0,
 suspended INTEGER NOT NULL DEFAULT 0, ostinato INTEGER NOT NULL DEFAULT 0,
 ease REAL NOT NULL DEFAULT 2.5, interval REAL NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0,
 UNIQUE(note_id,ordinal));
CREATE TABLE IF NOT EXISTS sr_sessions(
 id TEXT PRIMARY KEY, deck_id INTEGER REFERENCES sr_decks(id),
 started REAL NOT NULL, ended REAL, source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sr_reviews(
 id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES sr_cards(id),
 deck_id INTEGER NOT NULL REFERENCES sr_decks(id), session_id TEXT NOT NULL REFERENCES sr_sessions(id),
 reviewed REAL NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 4),
 duration_ms INTEGER NOT NULL, before TEXT NOT NULL, after TEXT NOT NULL,
 state_before INTEGER NOT NULL, previous_review REAL, retrievability REAL,
 undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS sr_media(
 filename TEXT PRIMARY KEY, original_name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS sr_notes_deck ON sr_notes(deck_id,deleted);
CREATE INDEX IF NOT EXISTS sr_cards_due ON sr_cards(deleted,suspended,state,due);
CREATE INDEX IF NOT EXISTS sr_cards_note ON sr_cards(note_id);
CREATE INDEX IF NOT EXISTS sr_reviews_day ON sr_reviews(deck_id,reviewed,undone);
CREATE INDEX IF NOT EXISTS sr_reviews_recent ON sr_reviews(reviewed);
CREATE INDEX IF NOT EXISTS sr_reviews_history ON sr_reviews(card_id,id);
CREATE INDEX IF NOT EXISTS sr_reviews_session ON sr_reviews(session_id,id);
'''


def day_bounds(now):
    local = datetime.fromtimestamp(now)
    date = (local - timedelta(hours=DAY_START)).date()
    return (datetime.combine(date, daytime(DAY_START)).timestamp(),
            datetime.combine(date + timedelta(days=1), daytime(DAY_START)).timestamp())


def parse_steps(text):
    values = []
    for token in str(text).lower().split():
        match = re.fullmatch(r'(\d+(?:[.,]\d+)?|[.,]\d+)([smhd]?)', token)
        if not match:
            raise ValueError('Passi non validi. Esempio: 10s 30s 1m 10m.')
        number, unit = match.groups()
        seconds = float(number.replace(',', '.')) * {'s':1,'m':60,'h':3600,'d':86400,'':60}[unit]
        if not math.isfinite(seconds) or not 1 <= seconds <= 36500*86400:
            raise ValueError('Ogni passo deve durare almeno un secondo.')
        values.append(timedelta(seconds=seconds))
    if len(values) > 20:
        raise ValueError('Usa al massimo 20 passi.')
    return tuple(values)


def validate_settings(values):
    settings = {**DEFAULTS, **values}
    retention = settings['retention']
    if not isinstance(retention, (int, float)) or not .70 <= retention <= .99:
        raise ValueError('La ritenzione deve essere tra 70% e 99%.')
    for key in ('new_limit', 'review_limit'):
        value = settings[key]
        if value is not None and (type(value) is not int or not 0 <= value <= 1000000):
            raise ValueError('Limite giornaliero non valido.')
    for key in ('learning', 'relearning'):
        parse_steps(settings[key])
    if type(settings['leech_threshold']) is not int or not 2 <= settings['leech_threshold'] <= 1000:
        raise ValueError('Soglia non valida: scegli un valore tra 2 e 1000.')
    settings['fsrs'] = bool(settings['fsrs'])
    settings['suspend_leeches'] = bool(settings['suspend_leeches'])
    return settings


def cloze_ordinals(text):
    matches = list(CLOZE.finditer(text))
    if not matches or any(not m[2].strip() or '{{' in m[2] for m in matches):
        raise ValueError('Inserisci almeno una lacuna, per esempio {{c1::你好::saluto}}.')
    remainder = CLOZE.sub('', text)
    if '{{' in remainder or '}}' in remainder:
        raise ValueError('Controlla le parentesi delle lacune. Le lacune annidate non sono supportate.')
    return sorted({int(m[1]) for m in matches})


def render_cloze(text, ordinal, answer=False):
    """Escape every user string; only this function can emit markup."""
    result, end = [], 0
    for match in CLOZE.finditer(text):
        result.append(html.escape(text[end:match.start()]))
        if int(match[1]) != ordinal:
            result.append(html.escape(match[2]))
        elif answer:
            result.append('<span style="color:#badfe2;font-weight:600">'+html.escape(match[2])+'</span>')
        else:
            result.append('<span style="color:#dcc6f0">['+html.escape(match[3] or '…')+']</span>')
        end = match.end()
    result.append(html.escape(text[end:]))
    return ''.join(result).replace('\n','<br>')


def validate_content(kind, content):
    if kind not in ('basic','cloze'):
        raise ValueError('Tipo di carta non supportato.')
    result = {'front':str(content.get('front','')).strip(), 'back':str(content.get('back','')).strip(),
              'front_media':list(content.get('front_media',[])), 'back_media':list(content.get('back_media',[]))}
    if any(len(result[key]) > 100000 for key in ('front','back')):
        raise ValueError('Testo troppo lungo (massimo 100.000 caratteri per lato).')
    for key in ('front_media','back_media'):
        if len(result[key]) > 12 or any(not isinstance(v,str) or not MEDIA.fullmatch(v) for v in result[key]):
            raise ValueError('Allegati non validi (massimo 12 per lato).')
    if not result['front'] and not result['front_media']:
        raise ValueError('Il fronte è vuoto.')
    if kind == 'basic' and not result['back'] and not result['back_media']:
        raise ValueError('Il retro è vuoto.')
    ordinals = cloze_ordinals(result['front']) if kind == 'cloze' else [0]
    return result, ordinals


def duration_label(seconds):
    if seconds < 60: return f'{max(1,round(seconds))} s'
    if seconds < 3600: return f'{seconds/60:g} min'
    if seconds < 86400: return f'{seconds/3600:.1f} h'.replace('.0 ', ' ')
    if seconds < 86400*30: return f'{round(seconds/86400)} g'
    if seconds < 86400*365: return f'{seconds/86400/30:.1f} mesi'
    return f'{seconds/86400/365:.1f} anni'


class StudyStore:
    def __init__(self, store):
        self.store, self.db = store, store.db
        self.media_root = store.root/'study-media'
        self.db.executescript(SCHEMA)

    def decks(self):
        return [dict(r) for r in self.db.execute('SELECT * FROM sr_decks WHERE archived=0 ORDER BY name')]

    def deck(self, deck_id):
        row = self.db.execute('SELECT * FROM sr_decks WHERE id=? AND archived=0',(deck_id,)).fetchone()
        if row is None: raise ValueError('Mazzo non trovato.')
        result = dict(row); result['settings'] = validate_settings(json.loads(result['settings']))
        result['parameters'] = json.loads(result['parameters']) if result['parameters'] else None
        return result

    def save_deck(self, name, settings=None, deck_id=None):
        name = name.strip()
        if not name:raise ValueError('Il nome del mazzo non può essere vuoto.')
        if len(name)>120:raise ValueError('Il nome del mazzo non può superare 120 caratteri.')
        duplicate=self.db.execute('SELECT id FROM sr_decks WHERE name=? COLLATE NOCASE',(name,)).fetchone()
        if duplicate and duplicate[0]!=deck_id:
            raise ValueError('Esiste già un mazzo con questo nome, anche nell’archivio.')
        old = self.deck(deck_id) if deck_id else None
        settings = validate_settings(settings if settings is not None else (old['settings'] if old else {}))
        with self.db:
            if old:
                self.db.execute('UPDATE sr_decks SET name=?,settings=? WHERE id=?',(name,json.dumps(settings),deck_id))
            else:
                deck_id = self.db.execute('INSERT INTO sr_decks(name,settings) VALUES(?,?)',(name,json.dumps(settings))).lastrowid
        return deck_id

    def archive_deck(self, deck_id):
        with self.db: self.db.execute('UPDATE sr_decks SET archived=1 WHERE id=?',(deck_id,))

    def restore_deck(self, deck_id):
        with self.db:self.db.execute('UPDATE sr_decks SET archived=0 WHERE id=?',(deck_id,))

    def save_note(self, deck_id, kind, content, note_id=None, now=None):
        self.deck(deck_id)
        now = time.time() if now is None else now
        content, ordinals = validate_content(kind,content)
        for key in ('front_media','back_media'):
            for filename in content[key]:
                if not self.media_path(filename).is_file(): raise ValueError('Un allegato non è disponibile.')
        with self.db:
            if note_id:
                current = self.db.execute('SELECT id FROM sr_notes WHERE id=? AND deleted=0',(note_id,)).fetchone()
                if current is None: raise ValueError('Carta non trovata.')
                self.db.execute('UPDATE sr_notes SET deck_id=?,kind=?,content=?,modified=? WHERE id=?',
                                (deck_id,kind,json.dumps(content,ensure_ascii=False),now,note_id))
                self.db.execute('UPDATE sr_cards SET deleted=1,revision=revision+1 WHERE note_id=?',(note_id,))
            else:
                note_id = self.db.execute('INSERT INTO sr_notes(deck_id,kind,content,created,modified) VALUES(?,?,?,?,?)',
                    (deck_id,kind,json.dumps(content,ensure_ascii=False),now,now)).lastrowid
            for ordinal in ordinals:
                self.db.execute('''INSERT INTO sr_cards(note_id,ordinal,due) VALUES(?,?,?)
                  ON CONFLICT(note_id,ordinal) DO UPDATE SET deleted=0''',(note_id,ordinal,now))
        return note_id

    def note(self, note_id):
        row = self.db.execute('SELECT * FROM sr_notes WHERE id=? AND deleted=0',(note_id,)).fetchone()
        if row is None: raise ValueError('Carta non trovata.')
        result = dict(row); result['content'] = json.loads(result['content']); return result

    def delete_note(self, note_id):
        with self.db:
            self.db.execute('UPDATE sr_notes SET deleted=1 WHERE id=?',(note_id,))
            self.db.execute('UPDATE sr_cards SET deleted=1,revision=revision+1 WHERE note_id=?',(note_id,))

    def browse(self, deck_id, query='', only_ostinati=False, offset=0, limit=100):
        rows = self.db.execute('''SELECT n.*, count(c.id) AS cards, max(c.ostinato) AS ostinato,
            min(c.suspended) AS suspended, max(c.difficulty) AS difficulty, min(c.due) AS due
            FROM sr_notes n JOIN sr_cards c ON c.note_id=n.id AND c.deleted=0
            WHERE n.deck_id=? AND n.deleted=0 AND instr(lower(n.content),lower(?))>0
            GROUP BY n.id HAVING (?=0 OR max(c.ostinato)=1)
            ORDER BY n.id DESC LIMIT ? OFFSET ?''',(deck_id,query,int(only_ostinati),min(100,limit),max(0,offset)))
        return [{**dict(r),'content':json.loads(r['content'])} for r in rows]

    def suspend(self, note_id, value):
        with self.db:
            self.db.execute('UPDATE sr_cards SET suspended=?,revision=revision+1 WHERE note_id=? AND deleted=0',
                            (int(bool(value)),note_id))

    def card(self, card_id):
        row = self.db.execute('''SELECT c.*,n.deck_id,n.kind,n.content FROM sr_cards c
          JOIN sr_notes n ON n.id=c.note_id JOIN sr_decks d ON d.id=n.deck_id
          WHERE c.id=? AND c.deleted=0 AND n.deleted=0 AND d.archived=0''',(card_id,)).fetchone()
        if row is None: raise ValueError('Carta non trovata.')
        return dict(row)

    def import_media(self, source):
        source = Path(source); suffix = source.suffix[1:].lower()
        if suffix not in MEDIA_TYPES: raise ValueError('Formato non supportato.')
        if not source.is_file() or source.stat().st_size > 32*1024*1024:
            raise ValueError('Scegli un file fino a 32 MB.')
        self.media_root.mkdir(exist_ok=True)
        digest = hashlib.sha256(); temp = self.media_root/(uuid.uuid4().hex+'.part')
        try:
            size = 0
            with source.open('rb') as reader, temp.open('wb') as writer:
                while chunk := reader.read(128*1024):
                    size += len(chunk)
                    if size > 32*1024*1024: raise ValueError('Il file supera 32 MB.')
                    digest.update(chunk); writer.write(chunk)
                writer.flush(); os.fsync(writer.fileno())
            if size == 0: raise ValueError('Il file è vuoto.')
            filename = digest.hexdigest()+'.'+suffix
            os.replace(temp,self.media_root/filename)
            with self.db:
                self.db.execute('INSERT OR IGNORE INTO sr_media VALUES(?,?,?,?)',
                                (filename,source.name,MEDIA_TYPES[suffix],size))
            return filename
        finally:
            temp.unlink(missing_ok=True)

    def media_path(self, filename):
        if not MEDIA.fullmatch(filename): raise ValueError('Allegato non valido.')
        path = self.media_root/filename
        if path.is_symlink(): raise ValueError('Allegato non valido.')
        return path

    def usage(self, deck_id, now):
        start, end = day_bounds(now)
        row = self.db.execute('''SELECT
          count(DISTINCT CASE WHEN state_before=0 THEN card_id END) AS new,
          count(DISTINCT CASE WHEN state_before=2 OR (state_before IN (1,3) AND previous_review<?)
            THEN card_id END) AS reviews
          FROM sr_reviews WHERE deck_id=? AND reviewed>=? AND reviewed<? AND undone=0''',
          (start,deck_id,start,end)).fetchone()
        return dict(row)

    def counts(self, deck_id, now=None):
        now = time.time() if now is None else now
        row = self.db.execute('''SELECT count(*) AS total,
          coalesce(sum(c.suspended),0) AS suspended,
          coalesce(sum(c.ostinato),0) AS ostinati,
          coalesce(sum(c.state=0 AND c.suspended=0),0) AS new,
          coalesce(sum(c.state=2 AND c.due<=? AND c.suspended=0),0) AS reviews,
          coalesce(sum(c.state IN (1,3) AND c.suspended=0),0) AS learning
          FROM sr_cards c JOIN sr_notes n ON n.id=c.note_id
          WHERE n.deck_id=? AND n.deleted=0 AND c.deleted=0''',(now,deck_id)).fetchone()
        result = dict(row); settings=self.deck(deck_id)['settings']; used=self.usage(deck_id,now)
        for key,setting in [('new','new_limit'),('reviews','review_limit')]:
            cap=settings[setting]
            if cap is not None: result[key]=min(result[key],max(0,cap-used[key]))
        if settings['review_limit'] is not None and used['reviews']>=settings['review_limit']: result['new']=0
        result['today']=self.db.execute('''SELECT count(*) FROM sr_reviews WHERE deck_id=?
          AND reviewed>=? AND reviewed<? AND undone=0''',(deck_id,*day_bounds(now))).fetchone()[0]
        result['retention']=self.db.execute('''SELECT avg(rating>1) FROM sr_reviews WHERE deck_id=?
          AND state_before=2 AND reviewed-previous_review>=86400 AND reviewed>=? AND undone=0''',
          (deck_id,now-30*86400)).fetchone()[0]
        return result

    def next_card(self, deck_id, prefer_new=False, now=None, exclude=()):
        now = time.time() if now is None else now
        settings=self.deck(deck_id)['settings']; used=self.usage(deck_id,now)
        review_allowed=settings['review_limit'] is None or used['reviews']<settings['review_limit']
        new_allowed=review_allowed and (settings['new_limit'] is None or used['new']<settings['new_limit'])
        base='''SELECT c.id FROM sr_cards c JOIN sr_notes n ON n.id=c.note_id
          WHERE n.deck_id=? AND n.deleted=0 AND c.deleted=0 AND c.suspended=0 AND c.due<=?'''
        args=[deck_id,now]
        if exclude:
            base+=' AND c.id NOT IN ('+','.join('?' for _ in exclude)+')'; args.extend(exclude)
        learning=base+' AND c.state IN (1,3)'
        learning_args=args[:]
        if not review_allowed:
            learning+=' AND c.last_review>=?'; learning_args.append(day_bounds(now)[0])
        row=self.db.execute(learning+' ORDER BY c.due,c.id LIMIT 1',learning_args).fetchone()
        if row: return self.card(row[0])
        for state in ([0,2] if prefer_new else [2,0]):
            if not (new_allowed if state==0 else review_allowed): continue
            row=self.db.execute(base+' AND c.state=? ORDER BY c.due,c.id LIMIT 1',[*args,state]).fetchone()
            if row: return self.card(row[0])
        return None

    def next_learning_due(self, deck_id, now=None):
        now=time.time() if now is None else now
        s=self.deck(deck_id)['settings']; used=self.usage(deck_id,now)
        restricted=s['review_limit'] is not None and used['reviews']>=s['review_limit']
        return self.db.execute('''SELECT min(c.due) FROM sr_cards c JOIN sr_notes n ON n.id=c.note_id
          WHERE n.deck_id=? AND n.deleted=0 AND c.deleted=0 AND c.suspended=0 AND c.state IN (1,3)
          AND (?=0 OR c.last_review>=?)''',(deck_id,int(restricted),day_bounds(now)[0])).fetchone()[0]

    def start_session(self, deck_id, source='study', now=None):
        ident=uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO sr_sessions VALUES(?,?,?,NULL,?)',
                            (ident,deck_id,time.time() if now is None else now,source))
        return ident

    def end_session(self, session_id, now=None):
        with self.db:
            self.db.execute('UPDATE sr_sessions SET ended=? WHERE id=? AND ended IS NULL',
                            (time.time() if now is None else now,session_id))
        return [r[0] for r in self.db.execute('SELECT DISTINCT deck_id FROM sr_reviews WHERE session_id=? AND undone=0',(session_id,))]

    def scheduler(self, deck_id):
        from fsrs import Scheduler
        deck=self.deck(deck_id); settings=deck['settings']
        kwargs=dict(desired_retention=settings['retention'], learning_steps=parse_steps(settings['learning']),
                    relearning_steps=parse_steps(settings['relearning']),enable_fuzzing=False)
        if deck['parameters']: kwargs['parameters']=deck['parameters']
        return Scheduler(**kwargs)

    def predict(self, row, rating, now):
        from fsrs import Card, Rating, State
        state = State(max(1,row['state']))
        utc=lambda ts:datetime.fromtimestamp(ts,timezone.utc) if ts is not None else None
        card=Card(card_id=row['id'],state=state,step=row['step'] if row['step'] is not None else (0 if state!=State.Review else None),
                  stability=row['stability'],difficulty=row['difficulty'],due=utc(row['due']),last_review=utc(row['last_review']))
        scheduler=self.scheduler(row['deck_id'])
        result,_=scheduler.review_card(card,Rating(rating),utc(now))
        after={key:row[key] for key in ('state','step','stability','difficulty','due','last_review','reps','lapses',
                                       'suspended','ostinato','ease','interval','revision')}
        after.update(state=int(result.state),step=result.step,stability=result.stability,difficulty=result.difficulty,
                     due=result.due.timestamp(),last_review=now,reps=row['reps']+1,revision=row['revision']+1)
        settings=self.deck(row['deck_id'])['settings']
        if row['state']==2 and rating==1:
            after['lapses']+=1
            if after['lapses']>=settings['leech_threshold']:
                after['ostinato']=1
                if settings['suspend_leeches']: after['suspended']=1
        if not settings['fsrs'] and after['state']==2:
            # Optional conventional interval scheduler. FSRS memory continues to
            # be recorded, so enabling it again does not erase the history.
            interval = max(1,row['interval'])
            if row['state']!=2 or rating==1: days=4 if rating==4 else 1
            else: days=max(1,round(interval*{2:1.2,3:row['ease'],4:row['ease']*1.3}[rating]))
            after['ease']=max(1.3,row['ease']+{1:-.2,2:-.15,3:0,4:.15}[rating])
            after['due']=now+min(36500,days)*86400
        after['interval']=(after['due']-now)/86400
        return after

    def review(self, card_id, rating, session_id, revision=None, now=None, duration_ms=0):
        if type(rating) is not int or rating not in (1,2,3,4): raise ValueError('Valutazione non valida.')
        now=time.time() if now is None else now
        with self.db:
            session=self.db.execute('SELECT * FROM sr_sessions WHERE id=? AND ended IS NULL',(session_id,)).fetchone()
            if session is None: raise ValueError('La sessione è terminata.')
            row=self.card(card_id)
            if row['suspended'] or (revision is not None and row['revision']!=revision):
                raise ValueError('La carta è cambiata. Riapri lo studio.')
            if session['deck_id'] is not None and row['deck_id']!=session['deck_id']: raise ValueError('Mazzo non valido.')
            if row['last_review'] is not None and now<row['last_review']:
                raise ValueError('L’orologio di sistema precede l’ultima risposta. Correggi l’ora prima di continuare.')
            after=self.predict(row,rating,now)
            before={key:row[key] for key in after}
            retrievability=self.retrievability(row,now)
            changed=self.db.execute('UPDATE sr_cards SET '+','.join(key+'=?' for key in after)+' WHERE id=? AND revision=?',
                                   [*after.values(),card_id,row['revision']])
            if changed.rowcount!=1: raise ValueError('La carta è cambiata. Riprova.')
            review_id=self.db.execute('''INSERT INTO sr_reviews(card_id,deck_id,session_id,reviewed,rating,duration_ms,
              before,after,state_before,previous_review,retrievability) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
              (card_id,row['deck_id'],session_id,now,rating,max(0,min(600000,int(duration_ms))),json.dumps(before),
               json.dumps(after),row['state'],row['last_review'],retrievability)).lastrowid
        return review_id,after

    def undo(self, session_id):
        with self.db:
            row=self.db.execute('SELECT * FROM sr_reviews WHERE session_id=? AND undone=0 ORDER BY id DESC LIMIT 1',(session_id,)).fetchone()
            if row is None: return None
            card=self.card(row['card_id']); after=json.loads(row['after'])
            if card['revision']!=after['revision']: raise ValueError('La carta è stata modificata dopo questa risposta.')
            before=json.loads(row['before'])
            self.db.execute('UPDATE sr_cards SET '+','.join(k+'=?' for k in before)+' WHERE id=?',
                            [*before.values(),card['id']])
            self.db.execute('UPDATE sr_reviews SET undone=1 WHERE id=?',(row['id'],))
            # Invalidate a fit that may have started after the session ended.
            self.db.execute('UPDATE sr_decks SET generation=generation+1,optimized_through=0 WHERE id=?',(row['deck_id'],))
            return card['id']

    def retrievability(self, row, now=None):
        if row['last_review'] is None or not row['stability']: return None
        from fsrs import Card
        now=time.time() if now is None else now
        card=Card(card_id=row['id'],stability=row['stability'],difficulty=row['difficulty'],
                  last_review=datetime.fromtimestamp(row['last_review'],timezone.utc))
        return self.scheduler(row['deck_id']).get_card_retrievability(card,datetime.fromtimestamp(now,timezone.utc))

    def hard_candidates(self, now=None, limit=3, exclude=(), exclude_notes=()):
        """Difficult native cards from today's studied decks; spaced extra reviews."""
        now=time.time() if now is None else now
        start,end=day_bounds(now)
        rows=self.db.execute('''WITH recent AS (
          SELECT card_id,count(*) AS recent_reviews,sum(rating=1) AS recent_failures,
          sum(rating=2) AS recent_hard,max(CASE WHEN rating=1 THEN reviewed ELSE 0 END) AS last_failure
          FROM sr_reviews WHERE reviewed>=? AND reviewed<=? AND undone=0 AND state_before=2
          AND previous_review<=reviewed-86400 GROUP BY card_id)
          SELECT c.id,c.note_id,n.deck_id,c.difficulty,c.lapses,c.reps,c.ease,
          (c.ostinato OR c.lapses>=coalesce(json_extract(d.settings,'$.leech_threshold'),16)) AS leech,
          coalesce(r.recent_reviews,0) AS recent_reviews,coalesce(r.recent_failures,0) AS recent_failures,
          coalesce(r.recent_hard,0) AS recent_hard,coalesce(r.last_failure,0) AS last_failure
          FROM sr_cards c JOIN sr_notes n ON n.id=c.note_id LEFT JOIN recent r ON r.card_id=c.id
          JOIN sr_decks d ON d.id=n.deck_id WHERE d.archived=0 AND n.deleted=0 AND c.deleted=0
          AND c.suspended=0 AND c.state IN (2,3) AND c.last_review<=?
          AND EXISTS(SELECT 1 FROM sr_reviews r WHERE r.deck_id=d.id AND r.reviewed>=? AND r.reviewed<? AND r.undone=0)
          ''',(now-30*86400,now,now-1800,start,min(end,now+1)))
        allowed={}
        def metadata():
            for row in rows:
                deck=row['deck_id']
                if deck not in allowed:
                    cap=self.deck(deck)['settings']['review_limit'];used=self.usage(deck,now)['reviews']
                    allowed[deck]=cap is None or used<cap
                if allowed[deck]:yield row
        from yun_jin_study_selection import select_candidates
        return [self.card(row['id']) for row in select_candidates(metadata(),limit,exclude,exclude_notes)]
