# SPDX-License-Identifier: GPL-3.0-or-later
"""Local calendar, wall-clock alarms and durable, bounded notification scheduling.

Dates stored without an offset follow the computer's local time. Named zones use
Qt's existing timezone database, including on Windows, without another package.
An occurrence is identified by its original local start, so the repeated autumn
hour and backward clock changes never produce a second notification.
"""
import calendar
import json
import math
import re
import time
import uuid
from collections import deque
from datetime import date, datetime, time as daytime, timedelta

from PyQt6.QtCore import QDate, QDateTime, QTime, QTimeZone

ALARM_GRACE = 10 * 60
EVENT_GRACE = 2 * 60 * 60
MAX_ITEMS = 2000
MAX_OCCURRENCES = 20000
MAX_EXCEPTIONS = 20000
MAX_QUERY_DAYS = 732
MAX_REMINDER = 30 * 24 * 60
COLORS = ('rose', 'lavender', 'blue', 'teal', 'amber')
_DATE_MAX = date(9999, 12, 31)
_DATE_MIN = date(1900, 1, 1)


def _date(value):
    try:
        result = value.date() if isinstance(value, datetime) else value if isinstance(value, date) else date.fromisoformat(str(value))
        if not _DATE_MIN <= result < _DATE_MAX:
            raise ValueError
        return result
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Data non valida.') from None


def _wall(value, all_day=False):
    try:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, date):
            result = datetime.combine(value, daytime())
        else:
            result = datetime.fromisoformat(str(value))
        if result.tzinfo is not None or not _DATE_MIN <= result.date() < _DATE_MAX:
            raise ValueError
        return datetime.combine(result.date(), daytime()) if all_day else result.replace(microsecond=0, fold=0)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Data o ora non valida.') from None


def _zone(name=''):
    if not isinstance(name, str) or len(name) > 100:
        raise ValueError('Fuso orario non valido.')
    try:
        zone = QTimeZone(name.encode('ascii')) if name else QTimeZone.systemTimeZone()
    except UnicodeEncodeError:
        raise ValueError('Fuso orario non valido.') from None
    if not zone.isValid():
        raise ValueError('Fuso orario non disponibile.')
    return zone


def wall_timestamp(value, timezone=''):
    """Resolve a local wall time: gap moves forward; overlap uses the first fold."""
    value = _wall(value)
    qt = QDateTime(QDate(value.year, value.month, value.day),
                   QTime(value.hour, value.minute, value.second), _zone(timezone),
                   QDateTime.TransitionResolution.RelativeToBefore)
    if not qt.isValid():
        raise ValueError('Data o ora non disponibile nel fuso scelto.')
    return float(qt.toSecsSinceEpoch())


def local_datetime(timestamp=None, timezone=''):
    timestamp = time.time() if timestamp is None else _timestamp(timestamp)
    qt = QDateTime.fromSecsSinceEpoch(int(timestamp), _zone(timezone))
    d, t = qt.date(), qt.time()
    return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute(), t.second())


def _timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -62135596800 <= value < 253402214400:
        raise ValueError('Data non valida.')
    return float(value)


def _integer(value, low, high, message):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(message)
    return value


def _title(value, kind):
    if not isinstance(value, str):
        raise ValueError('Scrivi un titolo.')
    value = value.strip()
    if not value:
        if kind == 'alarm':
            return 'Sveglia'
        raise ValueError('Il titolo non può essere vuoto.')
    if len(value) > 200:
        raise ValueError('Il titolo può contenere al massimo 200 caratteri.')
    return value


def _details(value):
    if not isinstance(value, str) or len(value) > 4000:
        raise ValueError('Le note possono contenere al massimo 4000 caratteri.')
    return value.strip()


def _color(value):
    if not isinstance(value, str) or (value not in COLORS and not re.fullmatch(r'#[0-9a-fA-F]{6}', value)):
        raise ValueError('Colore non valido.')
    return value


def normalize_recurrence(rule, start):
    """Small, explicit rule format, never a permissive or executable RRULE parser."""
    if rule is None or rule == {}:
        return None
    if not isinstance(rule, dict) or set(rule) - {'frequency', 'interval', 'weekdays', 'until', 'count'}:
        raise ValueError('Ripetizione non valida.')
    frequency = rule.get('frequency')
    if frequency == 'once':
        return None
    if frequency not in ('daily', 'weekly', 'monthly', 'yearly'):
        raise ValueError('Ripetizione non valida.')
    result = {'frequency': frequency,
              'interval': _integer(rule.get('interval', 1), 1, 100, 'Intervallo di ripetizione non valido.')}
    if frequency == 'weekly':
        days = rule.get('weekdays', [start.weekday()])
        if not isinstance(days, (list, tuple, set)) or not days:
            raise ValueError('Scegli almeno un giorno della settimana.')
        result['weekdays'] = sorted({_integer(n, 0, 6, 'Giorno della settimana non valido.') for n in days})
    elif rule.get('weekdays') not in (None, []):
        raise ValueError('I giorni della settimana richiedono una ripetizione settimanale.')
    if rule.get('until') is not None and rule.get('count') is not None:
        raise ValueError('Scegli una data finale oppure un numero di ripetizioni.')
    if rule.get('until') is not None:
        until = _date(rule['until'])
        if until < start.date():
            raise ValueError('La fine della ripetizione precede l’inizio.')
        result['until'] = until.isoformat()
    if rule.get('count') is not None:
        result['count'] = _integer(rule['count'], 1, 10000, 'Numero di ripetizioni non valido.')
    return result


def recurrence_dates(anchor, rule, first, last):
    """Yield dates in [first,last), seeking directly into old daily/weekly series.

    A monthly 31st skips months without that day; a yearly 29 February skips
    non-leap years. Counts count real occurrences, including later exceptions.
    """
    anchor, first, last = _date(anchor), _date(first), _date(last)
    if last <= first:
        return
    if not rule:
        if first <= anchor < last:
            yield anchor
        return
    first = max(first, anchor)
    until = date.fromisoformat(rule['until']) if rule.get('until') else _DATE_MAX
    last = min(last, until + timedelta(days=1) if until < _DATE_MAX else until)
    frequency, interval, count = rule['frequency'], rule.get('interval', 1), rule.get('count')
    if frequency == 'daily':
        index = max(0, ((first-anchor).days + interval-1)//interval)
        while count is None or index < count:
            ordinal = anchor.toordinal() + index * interval
            if ordinal >= last.toordinal():
                break
            yield date.fromordinal(ordinal)
            index += 1
    elif frequency == 'weekly':
        days = rule.get('weekdays', [anchor.weekday()])
        monday = anchor-timedelta(days=anchor.weekday())
        index = max(0, (first-monday).days // (7*interval))
        skipped = sum(day < anchor.weekday() for day in days)
        while True:
            base = monday.toordinal() + index*interval*7
            if base >= last.toordinal():
                break
            for offset, weekday in enumerate(days):
                ordinal = base+weekday
                if ordinal < anchor.toordinal():
                    continue
                number = index*len(days)+offset-skipped
                if count is not None and number >= count:
                    return
                if first.toordinal() <= ordinal < last.toordinal():
                    yield date.fromordinal(ordinal)
            index += 1
    else:
        # At most 10,000 counted occurrences; unbounded rules seek immediately.
        if frequency == 'monthly':
            anchor_index = anchor.year*12+anchor.month-1
            first_index = first.year*12+first.month-1
            index = 0 if count is not None else max(0, (first_index-anchor_index)//interval)
        else:
            index = 0 if count is not None else max(0, (first.year-anchor.year)//interval)
        number = 0
        while True:
            if frequency == 'monthly':
                year, month = divmod(anchor_index+index*interval, 12)
                month += 1
            else:
                year, month = anchor.year+index*interval, anchor.month
            if year > 9999 or (year, month) > (last.year, last.month):
                break
            index += 1
            if anchor.day > calendar.monthrange(year, month)[1]:
                continue
            candidate = date(year, month, anchor.day)
            if candidate >= last:
                break
            if count is not None and number >= count:
                break
            number += 1
            if candidate >= first:
                yield candidate


class AgendaStore:
    def __init__(self, store):
        self.store, self.db = store, store.db
        self._announced = set()
        self._items = None
        self._exceptions = None
        self._ready = None
        self._next = None
        self._planned_at = None
        self._last_wall = None
        self._last_monotonic = None
        self._zone_id = None
        self.revision = 0
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS agenda_items (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('alarm','event')),
                title TEXT NOT NULL, start_local TEXT NOT NULL, end_local TEXT NOT NULL,
                all_day INTEGER NOT NULL DEFAULT 0, timezone TEXT NOT NULL DEFAULT '',
                recurrence TEXT, reminder_minutes INTEGER, voice INTEGER NOT NULL DEFAULT 1,
                sound INTEGER NOT NULL DEFAULT 1, enabled INTEGER NOT NULL DEFAULT 1,
                snooze_minutes INTEGER NOT NULL DEFAULT 10, details TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT 'rose', created REAL NOT NULL, updated REAL NOT NULL,
                notify_from REAL NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS agenda_items_kind ON agenda_items(kind,enabled,start_local);
            CREATE TABLE IF NOT EXISTS agenda_exceptions (
                item_id TEXT NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
                occurrence_key TEXT NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0,
                start_local TEXT, overrides TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(item_id,occurrence_key));
            CREATE INDEX IF NOT EXISTS agenda_exception_dates ON agenda_exceptions(start_local);
            CREATE TABLE IF NOT EXISTS agenda_alerts (
                id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
                occurrence_key TEXT NOT NULL, scheduled_at REAL NOT NULL, due_at REAL NOT NULL,
                expires_at REAL NOT NULL, state TEXT NOT NULL CHECK(state IN ('pending','snoozed','dismissed','missed')),
                payload TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                notified_at REAL,
                UNIQUE(item_id,occurrence_key));
            CREATE INDEX IF NOT EXISTS agenda_alert_due ON agenda_alerts(state,due_at);
            CREATE INDEX IF NOT EXISTS agenda_alert_history ON agenda_alerts(updated);
            CREATE TABLE IF NOT EXISTS agenda_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        if 'notified_at' not in {row[1] for row in self.db.execute('PRAGMA table_info(agenda_alerts)')}:
            with self.db:self.db.execute('ALTER TABLE agenda_alerts ADD COLUMN notified_at REAL')
        if 'notify_from' not in {row[1] for row in self.db.execute('PRAGMA table_info(agenda_items)')}:
            with self.db:
                self.db.execute('ALTER TABLE agenda_items ADD COLUMN notify_from REAL NOT NULL DEFAULT 0')
                self.db.execute('UPDATE agenda_items SET notify_from=created')

    def invalidate(self):
        self._items = self._exceptions = self._planned_at = self._next = self._ready = None
        self.revision += 1

    def _decode(self, row):
        if row is None:
            return None
        result = dict(row)
        result['recurrence'] = json.loads(result['recurrence']) if result['recurrence'] else None
        for field in ('all_day', 'voice', 'sound', 'enabled'):
            result[field] = bool(result[field])
        if result['kind'] == 'alarm':
            result['clock'] = result['start_local'][11:16]
            result['on_date'] = result['start_local'][:10] if not result['recurrence'] else None
            result['weekdays'] = result['recurrence'].get('weekdays', list(range(7))) if result['recurrence'] else None
        return result

    def get(self, item_id):
        return self._decode(self.db.execute('SELECT * FROM agenda_items WHERE id=?', (item_id,)).fetchone())

    def _save(self, item, item_id, now):
        previous = self.get(item_id) if item_id else None
        if item_id and not previous:
            raise ValueError('Elemento non trovato.')
        if previous and previous['kind'] != item['kind']:
            raise ValueError('Tipo di elemento non valido.')
        if not previous and self.db.execute('SELECT count(*) FROM agenda_items').fetchone()[0] >= MAX_ITEMS:
            raise ValueError('Hai raggiunto il limite di 2000 elementi. Elimina quelli non più necessari.')
        item_id = item_id or uuid.uuid4().hex
        schedule_fields = ('start_local', 'end_local', 'timezone', 'recurrence', 'all_day')
        changed = previous and any(previous[key] != item[key] for key in schedule_fields)
        with self.db:
            if changed:
                self.db.execute('DELETE FROM agenda_exceptions WHERE item_id=?', (item_id,))
            if previous:
                if changed or previous['reminder_minutes']!=item['reminder_minutes'] or not item['enabled']:
                    self.db.execute("UPDATE agenda_alerts SET state='dismissed',updated=? WHERE item_id=? AND state IN ('pending','snoozed')", (now,item_id))
                else:
                    for row in self.db.execute("SELECT id,occurrence_key,payload FROM agenda_alerts WHERE item_id=? AND state IN ('pending','snoozed')",(item_id,)).fetchall():
                        payload=json.loads(row['payload'])
                        exception=self.db.execute('SELECT overrides FROM agenda_exceptions WHERE item_id=? AND occurrence_key=?',(item_id,row['occurrence_key'])).fetchone()
                        overrides=json.loads(exception[0]) if exception else {}
                        payload.update({key:overrides.get(key,item[key]) for key in ('title','voice','sound','details','color','snooze_minutes')})
                        self.db.execute('UPDATE agenda_alerts SET payload=?,updated=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),now,row['id']))
            columns = ['kind','title','start_local','end_local','all_day','timezone','recurrence',
                       'reminder_minutes','voice','sound','enabled','snooze_minutes','details','color']
            values = [json.dumps(item[k], separators=(',', ':')) if k == 'recurrence' and item[k] else item[k] for k in columns]
            if previous:
                self.db.execute('UPDATE agenda_items SET '+','.join(k+'=?' for k in columns)+',updated=? WHERE id=?', values+[now,item_id])
                if changed or (item['enabled'] and not previous['enabled']):
                    self.db.execute('UPDATE agenda_items SET notify_from=? WHERE id=?',(now,item_id))
            else:
                self.db.execute('INSERT INTO agenda_items (id,'+','.join(columns)+',created,updated,notify_from) VALUES ('+','.join('?' for _ in range(18))+')', [item_id]+values+[now,now,now])
        self.invalidate()
        return item_id

    def save_alarm(self, title='', clock='08:00', *, weekdays=None, on_date=None,
                   enabled=True, snooze_minutes=10, voice=True, sound=True,
                   alarm_id=None, now=None):
        now = time.time() if now is None else _timestamp(now)
        if not isinstance(clock, str) or not re.fullmatch(r'\d{2}:\d{2}', clock):
            raise ValueError('Ora non valida.')
        try:
            chosen_time = daytime.fromisoformat(clock)
        except ValueError:
            raise ValueError('Ora non valida.') from None
        current = local_datetime(now)
        day = _date(on_date) if on_date else current.date()
        start = datetime.combine(day, chosen_time)
        if weekdays is None:
            if not on_date and wall_timestamp(start) <= now:
                start += timedelta(days=1)
            if enabled and on_date and wall_timestamp(start) <= now:
                previous = self.get(alarm_id) if alarm_id else None
                if not previous or previous['start_local'] != start.isoformat():
                    raise ValueError('Scegli una data e un’ora future.')
            recurrence = None
        else:
            recurrence = normalize_recurrence({'frequency':'weekly','weekdays':weekdays}, start)
            previous=self.get(alarm_id) if alarm_id else None
            if previous and previous['kind']=='alarm' and previous['recurrence']==recurrence and previous['clock']==clock:
                start=_wall(previous['start_local'])
        item = dict(kind='alarm',title=_title(title,'alarm'),start_local=start.isoformat(),
                    end_local=(start+timedelta(minutes=1)).isoformat(),all_day=False,
                    timezone='',recurrence=recurrence,reminder_minutes=0,voice=bool(voice),
                    sound=bool(sound),enabled=bool(enabled),snooze_minutes=_integer(snooze_minutes,1,120,'Rinvio non valido.'),
                    details='',color='amber')
        return self._save(item,alarm_id,now)

    def save_event(self, title, start, end=None, *, all_day=False, recurrence=None,
                   reminder_minutes=10, voice=True, details='', timezone='',
                   color='rose', enabled=True, event_id=None, now=None):
        now = time.time() if now is None else _timestamp(now)
        start = _wall(start,all_day)
        end = _wall(end,all_day) if end is not None else start+timedelta(days=1) if all_day else start+timedelta(hours=1)
        if end <= start:
            raise ValueError('La fine deve essere successiva all’inizio.')
        if end-start > timedelta(days=366):
            raise ValueError('Un impegno può durare al massimo un anno.')
        _zone(timezone)
        if reminder_minutes is not None:
            _integer(reminder_minutes,0,MAX_REMINDER,'Anticipo dell’avviso non valido.')
        item = dict(kind='event',title=_title(title,'event'),start_local=start.isoformat(),end_local=end.isoformat(),
                    all_day=bool(all_day),timezone=timezone,recurrence=normalize_recurrence(recurrence,start),
                    reminder_minutes=reminder_minutes,voice=bool(voice),sound=True,enabled=bool(enabled),
                    snooze_minutes=10,details=_details(details),color=_color(color))
        return self._save(item,event_id,now)

    def events(self):
        return [self._decode(row) for row in self.db.execute("SELECT * FROM agenda_items WHERE kind='event' ORDER BY start_local,title")]

    def alarms(self, now=None):
        now = time.time() if now is None else _timestamp(now)
        result = [self._decode(row) for row in self.db.execute("SELECT * FROM agenda_items WHERE kind='alarm' ORDER BY substr(start_local,12,5),title")]
        for item in result:
            next_one = self.next_occurrence(item['id'],now) if item['enabled'] else None
            item['next_at'] = next_one['start'] if next_one else None
        return result

    def set_enabled(self, item_id, enabled, now=None):
        now=time.time() if now is None else _timestamp(now)
        item = self.get(item_id)
        if not item:
            raise ValueError('Elemento non trovato.')
        with self.db:
            if enabled and item['kind']=='alarm' and not item['recurrence'] and wall_timestamp(item['start_local'])<=now:
                start=datetime.combine(local_datetime(now).date(),_wall(item['start_local']).time())
                if wall_timestamp(start)<=now:start+=timedelta(days=1)
                self.db.execute('UPDATE agenda_items SET start_local=?,end_local=? WHERE id=?',(start.isoformat(),(start+timedelta(minutes=1)).isoformat(),item_id))
            self.db.execute('UPDATE agenda_items SET enabled=?,updated=? WHERE id=?', (bool(enabled),now,item_id))
            if enabled and not item['enabled']:
                self.db.execute('UPDATE agenda_items SET notify_from=? WHERE id=?',(now,item_id))
            if not enabled:
                self.db.execute("UPDATE agenda_alerts SET state='dismissed',updated=? WHERE item_id=? AND state IN ('pending','snoozed')", (now,item_id))
        self.invalidate()

    def delete(self, item_id, occurrence_key=None):
        if occurrence_key is not None:
            return self.skip_occurrence(item_id,occurrence_key)
        with self.db:
            self.db.execute('DELETE FROM agenda_items WHERE id=?',(item_id,))
        self.invalidate()

    def _validate_occurrence(self, item_id, key):
        item = self.get(item_id)
        if not item:
            raise ValueError('Elemento non trovato.')
        start = _wall(key)
        anchor = _wall(item['start_local'])
        if start.time() != anchor.time() or start.date() not in recurrence_dates(anchor.date(),item['recurrence'],start.date(),start.date()+timedelta(days=1)):
            raise ValueError('Occorrenza non valida.')
        return item,start.isoformat()

    def skip_occurrence(self, item_id, occurrence_key):
        _, key = self._validate_occurrence(item_id,occurrence_key)
        self._exception_capacity(item_id,key)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO agenda_exceptions VALUES (?,?,1,NULL,?)',(item_id,key,'{}'))
            self.db.execute("UPDATE agenda_alerts SET state='dismissed',updated=? WHERE item_id=? AND occurrence_key=?",(time.time(),item_id,key))
        self.invalidate()

    def save_exception(self, item_id, occurrence_key, **overrides):
        item,key = self._validate_occurrence(item_id,occurrence_key)
        self._exception_capacity(item_id,key)
        if item['kind'] != 'event':
            raise ValueError('Per una sveglia modifica la ripetizione completa.')
        allowed = {'title','start_local','end_local','all_day','details','reminder_minutes','voice','color'}
        if set(overrides)-allowed:
            raise ValueError('Modifica non valida.')
        existing = self.db.execute('SELECT overrides FROM agenda_exceptions WHERE item_id=? AND occurrence_key=?',(item_id,key)).fetchone()
        previous_changes = json.loads(existing[0]) if existing else {}
        changes = dict(previous_changes)
        changes.update(overrides)
        if 'title' in changes:changes['title'] = _title(changes['title'],'event')
        if 'details' in changes:changes['details'] = _details(changes['details'])
        if 'color' in changes:changes['color'] = _color(changes['color'])
        if 'reminder_minutes' in changes and changes['reminder_minutes'] is not None:
            _integer(changes['reminder_minutes'],0,MAX_REMINDER,'Anticipo dell’avviso non valido.')
        all_day = bool(changes.get('all_day',item['all_day']))
        start = _wall(changes.get('start_local',key),all_day)
        duration = _wall(item['end_local'])-_wall(item['start_local'])
        end = _wall(changes.get('end_local',start+duration),all_day)
        if end <= start or end-start > timedelta(days=366):
            raise ValueError('La fine deve essere successiva all’inizio, entro un anno.')
        changes.update(start_local=start.isoformat(),end_local=end.isoformat(),all_day=all_day)
        previous_start=_wall(previous_changes.get('start_local',key),previous_changes.get('all_day',item['all_day']))
        previous_end=_wall(previous_changes.get('end_local',previous_start+duration),previous_changes.get('all_day',item['all_day']))
        timing_changed=(start!=previous_start or end!=previous_end or
                        changes.get('reminder_minutes',item['reminder_minutes'])!=previous_changes.get('reminder_minutes',item['reminder_minutes']))
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO agenda_exceptions VALUES (?,?,0,?,?)',(item_id,key,start.isoformat(),json.dumps(changes,ensure_ascii=False)))
            if timing_changed:
                self.db.execute("DELETE FROM agenda_alerts WHERE item_id=? AND occurrence_key=? AND state!='dismissed'",(item_id,key))
            else:
                for row in self.db.execute("SELECT id,payload FROM agenda_alerts WHERE item_id=? AND occurrence_key=? AND state IN ('pending','snoozed')",(item_id,key)).fetchall():
                    payload=json.loads(row['payload'])
                    payload.update({field:changes.get(field,item[field]) for field in ('title','voice','details','color','all_day')})
                    self.db.execute('UPDATE agenda_alerts SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),row['id']))
        self.invalidate()

    def _exception_capacity(self,item_id,key):
        if self.db.execute('SELECT 1 FROM agenda_exceptions WHERE item_id=? AND occurrence_key=?',(item_id,key)).fetchone():return
        if self.db.execute('SELECT count(*) FROM agenda_exceptions').fetchone()[0]>=MAX_EXCEPTIONS:
            raise ValueError('Troppe modifiche alle ripetizioni. Elimina le serie non più necessarie.')

    def _load(self):
        if self._items is None:
            self._items = [self._decode(row) for row in self.db.execute('SELECT * FROM agenda_items WHERE enabled=1 ORDER BY id')]
        if self._exceptions is None:
            self._exceptions = {}
            for row in self.db.execute('SELECT * FROM agenda_exceptions'):
                self._exceptions.setdefault(row['item_id'],{})[row['occurrence_key']] = (bool(row['cancelled']),json.loads(row['overrides']))
        return self._items

    def _occurrence(self, item, day, changes=None, original_key=None):
        anchor,end_anchor = _wall(item['start_local']),_wall(item['end_local'])
        start = datetime.combine(day,anchor.time())
        key = original_key or start.isoformat()
        result = {k:item[k] for k in ('id','kind','title','all_day','timezone','recurrence','reminder_minutes','voice','sound','snooze_minutes','details','color','enabled')}
        result.update(item_id=item['id'],occurrence_key=key,start_local=start.isoformat(),end_local=(start+(end_anchor-anchor)).isoformat(),exception=False)
        if changes:
            result.update(changes)
            result['exception'] = True
        result['start'] = wall_timestamp(result['start_local'],item['timezone'])
        result['end'] = wall_timestamp(result['end_local'],item['timezone'])
        # A gap can normalize both ends to the same instant. Preserve duration
        # rather than producing a zero/negative appointment in the display.
        if result['end'] <= result['start']:
            result['end'] = result['start']+max(1,(_wall(result['end_local'])-_wall(result['start_local'])).total_seconds())
        return result

    def _between(self, item, first, last):
        """Occurrences overlapping an epoch interval, including moved exceptions."""
        self._load()
        exceptions = self._exceptions.get(item['id'],{})
        anchor,end = _wall(item['start_local']),_wall(item['end_local'])
        first_day = max(_DATE_MIN,local_datetime(first,item['timezone']).date()-timedelta(days=(end-anchor).days+1))
        last_day = min(_DATE_MAX-timedelta(days=1),local_datetime(last,item['timezone']).date()+timedelta(days=2))
        seen = set()
        for day in recurrence_dates(anchor.date(),item['recurrence'],first_day,last_day):
            key = datetime.combine(day,anchor.time()).isoformat()
            seen.add(key)
            cancelled,changes = exceptions.get(key,(False,{}))
            if cancelled:continue
            occurrence = self._occurrence(item,day,changes,key)
            if occurrence['start'] < last and occurrence['end'] > first:
                yield occurrence
        for key,(cancelled,changes) in exceptions.items():
            if key in seen or cancelled or not changes:continue
            occurrence = self._occurrence(item,_wall(key).date(),changes,key)
            if occurrence['start'] < last and occurrence['end'] > first:
                yield occurrence

    def occurrences(self, start_date, end_date, include_alarms=False):
        first,last = _date(start_date),_date(end_date)
        if last <= first or (last-first).days > MAX_QUERY_DAYS:
            raise ValueError('Scegli un intervallo di calendario non superiore a due anni.')
        lower,upper = wall_timestamp(datetime.combine(first,daytime())),wall_timestamp(datetime.combine(last,daytime()))
        result = []
        for item in self._load():
            if item['kind']=='alarm' and not include_alarms:continue
            result.extend(self._between(item,lower,upper))
            if len(result)>MAX_OCCURRENCES:
                raise ValueError('Troppi impegni nell’intervallo scelto. Seleziona un periodo più breve.')
        return sorted(result,key=lambda x:(x['start'],not x['all_day'],x['title'],x['item_id']))

    def next_occurrence(self, item_id, now=None):
        now = time.time() if now is None else _timestamp(now)
        item = self.get(item_id)
        if not item or not item['enabled']:return None
        return self._next_occurrence(item,now)

    def _next_occurrence(self, item, after, include_exceptions=True):
        self._load()
        anchor = _wall(item['start_local'])
        exceptions = self._exceptions.get(item['id'],{})
        best = None
        if include_exceptions:
            for key,(cancelled,changes) in exceptions.items():
                if cancelled or not changes:continue
                candidate = self._occurrence(item,_wall(key).date(),changes,key)
                if candidate['start'] >= after and (best is None or candidate['start']<best['start']):best=candidate
        first = max(anchor.date(),local_datetime(after,item['timezone']).date()-timedelta(days=1))
        for day in recurrence_dates(anchor.date(),item['recurrence'],first,_DATE_MAX-timedelta(days=1)):
            key = datetime.combine(day,anchor.time()).isoformat()
            if key in exceptions:continue
            candidate = self._occurrence(item,day)
            if candidate['start']>=after:
                if best is None or candidate['start']<best['start']:best=candidate
                break
        return best

    def _latest_occurrence(self, item, before, include_exceptions=True):
        rule = item['recurrence']
        if not rule:
            days = 2
            lower = wall_timestamp(item['start_local'],item['timezone'])-1
        else:
            days = {'daily':1,'weekly':7,'monthly':62,'yearly':1461}[rule['frequency']]*rule.get('interval',1)+2
            lower = max(wall_timestamp(item['start_local'],item['timezone'])-1,before-days*86400)
        best = None
        for candidate in self._between(item,lower,before+1):
            if not include_exceptions and candidate['exception']:continue
            if candidate['start']<=before and (best is None or candidate['start']>best['start']):best=candidate
        return best

    def _notification_time(self, occurrence):
        minutes = occurrence['reminder_minutes']
        return None if minutes is None else occurrence['start']-minutes*60

    def _remember_alert(self, item, occurrence, now):
        due = self._notification_time(occurrence)
        if due is None or due>now or occurrence['start']<max(item['created'],item['notify_from'])-1:
            return
        grace = ALARM_GRACE if item['kind']=='alarm' else EVENT_GRACE
        expiry = due+grace
        # For appointment notices, an ended event is no longer actionable.
        if item['kind']=='event':expiry=min(expiry,occurrence['end'])
        state = 'pending' if now<=expiry else 'missed'
        payload = {key:occurrence[key] for key in ('title','kind','voice','sound','details','snooze_minutes','all_day','start_local','end_local','color')}
        inserted=self.db.execute('''INSERT OR IGNORE INTO agenda_alerts
            (id,item_id,occurrence_key,scheduled_at,due_at,expires_at,state,payload,created,updated)
            VALUES (?,?,?,?,?,?,?,?,?,?)''', (uuid.uuid4().hex,item['id'],occurrence['occurrence_key'],occurrence['start'],due,expiry,state,
            json.dumps(payload,ensure_ascii=False),now,now)).rowcount
        if inserted:
            self.db.execute("""UPDATE agenda_alerts SET state='missed',updated=?
                WHERE item_id=? AND occurrence_key!=? AND scheduled_at<=?
                AND state IN ('pending','snoozed')""",(now,item['id'],occurrence['occurrence_key'],occurrence['start']))
        if inserted and item['kind']=='alarm' and not item['recurrence']:
            self.db.execute('UPDATE agenda_items SET enabled=0 WHERE id=?',(item['id'],))
            self._items=None

    def _scan(self, now):
        next_due = None
        changes_before=self.db.total_changes
        with self.db:
            self.db.execute("UPDATE agenda_alerts SET state='missed',updated=? WHERE state IN ('pending','snoozed') AND notified_at IS NULL AND expires_at<?",(now,now))
            self.db.execute("UPDATE agenda_alerts SET state='pending',updated=? WHERE state='snoozed' AND due_at<=? AND expires_at>=?",(now,now,now))
            for item in self._load():
                if item['reminder_minutes'] is None and not self._exceptions.get(item['id']):continue
                offset = (item['reminder_minutes'] or 0)*60
                # Latest due notice only: resuming after days never rings a
                # backlog, while its latest missed occurrence stays inspectable.
                latest = self._latest_occurrence(item,now+offset,False) if item['reminder_minutes'] is not None else None
                for key,(cancelled,changes) in self._exceptions.get(item['id'],{}).items():
                    if cancelled or not changes:continue
                    occurrence=self._occurrence(item,_wall(key).date(),changes,key)
                    due=self._notification_time(occurrence)
                    if due is None:continue
                    if due<=now:
                        if latest is None or due>self._notification_time(latest):latest=occurrence
                    else:next_due=due if next_due is None else min(next_due,due)
                if latest:self._remember_alert(item,latest,now)
                upcoming = self._next_occurrence(item,now+offset+1,False) if item['reminder_minutes'] is not None else None
                if upcoming:
                    due=self._notification_time(upcoming)
                    if due is not None and due>now:next_due=due if next_due is None else min(next_due,due)
            row=self.db.execute("SELECT min(due_at) FROM agenda_alerts WHERE state='snoozed'").fetchone()
            if row[0] is not None:next_due=row[0] if next_due is None else min(next_due,row[0])
            # Closed history is bounded; unresolved alerts remain until handled.
            self.db.execute("DELETE FROM agenda_alerts WHERE state IN ('dismissed','missed') AND updated<?",(now-90*86400,))
            self.db.execute("DELETE FROM agenda_alerts WHERE id IN (SELECT id FROM agenda_alerts WHERE state IN ('dismissed','missed') ORDER BY updated DESC LIMIT -1 OFFSET 4000)")
        rows=self.db.execute("SELECT * FROM agenda_alerts WHERE state='pending' ORDER BY due_at LIMIT 2000").fetchall()
        self._announced.intersection_update(row['id'] for row in rows)
        self._ready=deque(self._alert(row) for row in rows if row['id'] not in self._announced)
        self._next,self._planned_at=next_due,now
        if self.db.total_changes!=changes_before:self.revision+=1

    def next_deadline(self, now=None):
        now=time.time() if now is None else _timestamp(now)
        if self._planned_at is None or now<self._planned_at or now-self._planned_at>=60 or (self._next is not None and now>=self._next):
            self._scan(now)
        return self._next

    def poll(self, now=None, limit=20):
        now=time.time() if now is None else _timestamp(now)
        _integer(limit,1,200,'Numero di avvisi non valido.')
        monotonic=time.monotonic()
        zone=bytes(QTimeZone.systemTimeZoneId())
        clock_jump=self._last_wall is not None and abs((now-self._last_wall)-(monotonic-self._last_monotonic))>3
        if clock_jump or zone!=self._zone_id:self._planned_at=None
        self._last_wall,self._last_monotonic,self._zone_id=now,monotonic,zone
        self.next_deadline(now)
        if self._ready is None:
            self._ready=deque(self._alert(row) for row in self.db.execute("SELECT * FROM agenda_alerts WHERE state='pending' ORDER BY due_at LIMIT 2000") if row['id'] not in self._announced)
        result=[]
        while self._ready and len(result)<limit:
            alert=self._ready.popleft()
            if alert['id'] not in self._announced:
                alert['restored']=alert['notified_at'] is not None
                with self.db:
                    self.db.execute('UPDATE agenda_alerts SET notified_at=? WHERE id=?',(now,alert['id']))
                self._announced.add(alert['id']);result.append(alert)
        return result

    def _alert(self,row):
        if not row:return None
        result=dict(row)
        result.update(json.loads(result.pop('payload')))
        result['alert_id']=result['id']
        return result

    def alerts(self, include_dismissed=False, limit=100):
        _integer(limit,1,4000,'Numero di avvisi non valido.')
        clause='' if include_dismissed else "WHERE state!='dismissed'"
        return [self._alert(row) for row in self.db.execute('SELECT * FROM agenda_alerts '+clause+' ORDER BY scheduled_at DESC LIMIT ?',(limit,))]

    def pending_alerts(self):
        return [self._alert(row) for row in self.db.execute("SELECT * FROM agenda_alerts WHERE state IN ('pending','snoozed') ORDER BY due_at LIMIT 2000")]

    def missed_alerts(self, limit=100):
        _integer(limit,1,4000,'Numero di avvisi non valido.')
        return [self._alert(row) for row in self.db.execute("SELECT * FROM agenda_alerts WHERE state='missed' ORDER BY scheduled_at DESC LIMIT ?",(limit,))]

    def dismiss(self, alert_id):
        with self.db:
            self.db.execute("UPDATE agenda_alerts SET state='dismissed',updated=? WHERE id=?",(time.time(),alert_id))
        self._announced.discard(alert_id)
        self._planned_at=self._ready=None
        self.revision+=1

    def snooze(self, alert_id, minutes=None, now=None):
        now=time.time() if now is None else _timestamp(now)
        row=self.db.execute('SELECT * FROM agenda_alerts WHERE id=?',(alert_id,)).fetchone()
        if not row or row['state'] not in ('pending','snoozed'):
            raise ValueError('Avviso non più attivo.')
        alert=self._alert(row)
        minutes=alert['snooze_minutes'] if minutes is None else _integer(minutes,1,120,'Rinvio non valido.')
        due=now+minutes*60
        grace=ALARM_GRACE if alert['kind']=='alarm' else EVENT_GRACE
        with self.db:
            self.db.execute("UPDATE agenda_alerts SET state='snoozed',due_at=?,expires_at=?,updated=?,notified_at=NULL WHERE id=?",(due,due+grace,now,alert_id))
        self._announced.discard(alert_id)
        self._planned_at=self._ready=None
        self.revision+=1
        return due
