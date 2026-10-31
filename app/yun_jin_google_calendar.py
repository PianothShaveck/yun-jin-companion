# SPDX-License-Identifier: GPL-3.0-or-later
"""Durable, incremental, bidirectional Calendar synchronization.

One worker owns its own Store/SQLite connection. Remote writes never hold a DB
lock. Persisted links are an outbox: a changed/missing local item differs from
its acknowledged base until the remote operation succeeds, even across restart.
"""
from yun_jin_i18n import tr
import json
import time
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from yun_jin_google_codec import FIELDS, decode, encode, merge, read_time, write_time
from yun_jin_google_auth import GoogleError, Cancelled
from yun_jin_agenda import _zone


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


class GoogleStore:
    def __init__(self, store):
        self.store, self.db, self.agenda = store, store.db, store.agenda
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS google_accounts (
            id TEXT PRIMARY KEY, email TEXT NOT NULL, connected INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS google_calendars (
            account TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL,
            zone TEXT NOT NULL, selected INTEGER NOT NULL DEFAULT 0, token TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(account,id));
          CREATE TABLE IF NOT EXISTS google_links (
            item TEXT PRIMARY KEY, account TEXT NOT NULL, calendar TEXT NOT NULL,
            remote TEXT NOT NULL, base TEXT NOT NULL DEFAULT 'null', etag TEXT NOT NULL DEFAULT '',
            readonly INTEGER NOT NULL DEFAULT 0, url TEXT NOT NULL DEFAULT '',
            UNIQUE(account,calendar,remote));
          CREATE TABLE IF NOT EXISTS google_remote (
            account TEXT NOT NULL, calendar TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(account,calendar,id));
          CREATE TABLE IF NOT EXISTS google_conflicts (
            item TEXT PRIMARY KEY, remote TEXT NOT NULL, created REAL NOT NULL);
        ''')
        columns = {r[1] for r in self.db.execute('PRAGMA table_info(google_calendars)')}
        if 'reminders' not in columns:
            self.db.execute("ALTER TABLE google_calendars ADD COLUMN reminders TEXT NOT NULL DEFAULT '[]'")
        if not self.store.preference('google_profile', ''):
            self.store.set_preference('google_profile', uuid.uuid4().hex)

    def account(self, account, email):
        with self.db:
            self.db.execute('INSERT INTO google_accounts VALUES (?,?,1) ON CONFLICT(id) DO UPDATE SET email=excluded.email,connected=1', (account, email))

    def set_calendars(self, account, calendars):
        with self.db:
            for item in calendars:
                self.db.execute('''INSERT INTO google_calendars (account,id,name,role,zone,reminders) VALUES (?,?,?,?,?,?)
                    ON CONFLICT(account,id) DO UPDATE SET name=excluded.name,role=excluded.role,zone=excluded.zone,reminders=excluded.reminders''',
                    (account, item['id'], item.get('summaryOverride', item.get('summary', item['id'])),
                     item.get('accessRole', 'reader'), item.get('timeZone', 'UTC'), dump(item.get('defaultReminders', []))))
            available = {item['id'] for item in calendars}
            for row in self.db.execute('SELECT id FROM google_calendars WHERE account=?', (account,)).fetchall():
                if row[0] not in available:
                    self.db.execute('UPDATE google_calendars SET role=?,selected=0 WHERE account=? AND id=?', ('none', account, row[0]))

    def calendars(self, selected=False):
        return [dict(row) for row in self.db.execute('''SELECT c.*,a.email FROM google_calendars c
            JOIN google_accounts a ON a.id=c.account WHERE a.connected=1''' + (' AND c.selected=1' if selected else '') + ' ORDER BY a.email,c.name')]

    def select(self, account, calendar, selected):
        with self.db:
            self.db.execute('UPDATE google_calendars SET selected=? WHERE account=? AND id=?', (bool(selected), account, calendar))

    def link(self, item):
        row = self.db.execute('SELECT * FROM google_links WHERE item=?', (item,)).fetchone()
        return dict(row) if row else None

    def readonly(self, item):
        row = self.db.execute('''SELECT l.readonly,c.role,a.connected FROM google_links l
            LEFT JOIN google_calendars c ON c.account=l.account AND c.id=l.calendar
            LEFT JOIN google_accounts a ON a.id=l.account WHERE l.item=?''', (item,)).fetchone()
        return bool(row and (row[0] or row[1] not in ('owner', 'writer') or not row[2]))

    def assign(self, item, account, calendar):
        if not self.agenda.get(item) or self.agenda.get(item)['kind'] != 'event':
            raise ValueError(tr('Impegno non trovato.'))
        row = self.db.execute('''SELECT c.role FROM google_calendars c JOIN google_accounts a ON a.id=c.account
            WHERE c.account=? AND c.id=? AND c.selected=1 AND a.connected=1''', (account, calendar)).fetchone()
        if not row or row[0] not in ('owner', 'writer'):
            raise ValueError(tr('Calendario in sola lettura.'))
        existing = self.link(item)
        if existing:
            if (existing['account'], existing['calendar']) == (account, calendar):
                return
            raise ValueError(tr('Crea una copia per cambiare calendario.'))
        with self.db:
            self.db.execute('INSERT INTO google_links (item,account,calendar,remote) VALUES (?,?,?,?)',
                            (item, account, calendar, uuid.uuid4().hex))

    def snapshot(self, item):
        source = self.agenda.get(item)
        if source is None:
            return None
        result = {key: source[key] for key in FIELDS}
        result['timezone'] = result['timezone'] or bytes(_zone('').id()).decode() or 'UTC'
        result['exceptions'] = {}
        duration = datetime.fromisoformat(source['end_local']) - datetime.fromisoformat(source['start_local'])
        for row in self.db.execute('SELECT * FROM agenda_exceptions WHERE item_id=? ORDER BY occurrence_key', (item,)):
            if row['cancelled']:
                result['exceptions'][row['occurrence_key']] = {'cancelled': True}
            else:
                value = {key: result[key] for key in FIELDS if key != 'recurrence'}
                value.update(start_local=row['occurrence_key'], end_local=(datetime.fromisoformat(row['occurrence_key']) + duration).isoformat())
                value.update({key: val for key, val in json.loads(row['overrides']).items() if key in value})
                result['exceptions'][row['occurrence_key']] = {'cancelled': False, 'value': value}
        return result

    def _apply(self, item, value):
        """Caller holds the write transaction; never overwrite a stale GUI edit."""
        previous = self.agenda.get(item)
        if value is None:
            self.db.execute('DELETE FROM agenda_items WHERE id=?', (item,))
            return
        now = time.time()
        fields = dict(value)
        fields.pop('exceptions', None)
        fields['recurrence'] = dump(fields['recurrence']) if fields['recurrence'] else None
        if previous:
            schedule = any(previous[k] != value[k] for k in ('start_local','end_local','all_day','timezone','recurrence','reminder_minutes'))
            self.db.execute('UPDATE agenda_items SET ' + ','.join(key+'=?' for key in fields) + ',updated=? WHERE id=?', [*fields.values(), now, item])
            if schedule:
                self.db.execute("DELETE FROM agenda_alerts WHERE item_id=? AND state!='dismissed'", (item,))
                self.db.execute('UPDATE agenda_items SET notify_from=? WHERE id=?', (now, item))
            else:
                for alert in self.db.execute("SELECT id,payload FROM agenda_alerts WHERE item_id=? AND state IN ('pending','snoozed')", (item,)).fetchall():
                    payload = json.loads(alert['payload'])
                    payload.update(title=value['title'], details=value['details'])
                    self.db.execute('UPDATE agenda_alerts SET payload=? WHERE id=?', (dump(payload), alert['id']))
        else:
            if self.db.execute('SELECT count(*) FROM agenda_items').fetchone()[0] >= 2000:
                raise ValueError(tr('Hai raggiunto il limite di 2000 elementi. Elimina quelli non più necessari.'))
            fields.update(id=item, kind='event', created=now, updated=now, notify_from=now)
            self.db.execute('INSERT INTO agenda_items ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')', list(fields.values()))
        old = {row['occurrence_key']: (bool(row['cancelled']), json.loads(row['overrides'])) for row in self.db.execute('SELECT * FROM agenda_exceptions WHERE item_id=?', (item,))}
        for key, exception in value.get('exceptions', {}).items():
            overrides = exception.get('value', {})
            current = (exception['cancelled'], overrides)
            if old.pop(key, None) != current:
                self.db.execute('INSERT OR REPLACE INTO agenda_exceptions VALUES (?,?,?,?,?)', (item, key, exception['cancelled'], overrides.get('start_local'), dump(overrides)))
                self.db.execute("DELETE FROM agenda_alerts WHERE item_id=? AND occurrence_key=? AND state!='dismissed'", (item, key))
        for key in old:
            self.db.execute('DELETE FROM agenda_exceptions WHERE item_id=? AND occurrence_key=?', (item, key))
            self.db.execute("DELETE FROM agenda_alerts WHERE item_id=? AND occurrence_key=? AND state!='dismissed'", (item, key))

    def conflicts(self):
        return [dict(row) for row in self.db.execute('''SELECT f.*,a.title FROM google_conflicts f
            LEFT JOIN agenda_items a ON a.id=f.item ORDER BY f.created''')]

    def resolve(self, item, choice):
        if choice not in ('local', 'remote', 'both'):
            raise ValueError('Invalid conflict resolution')
        row = self.db.execute('SELECT remote FROM google_conflicts WHERE item=?', (item,)).fetchone()
        if not row:
            return
        remote = json.loads(row[0])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            local = self.snapshot(item)
            if choice == 'both' and local is not None:
                self._apply(uuid.uuid4().hex, local)  # No link: this copy never uploads.
            if choice != 'local':
                self._apply(item, remote)
            self.db.execute('UPDATE google_links SET base=? WHERE item=?', (dump(remote), item))
            if choice=='local' and remote is None and local is not None:
                self.db.execute('UPDATE google_links SET remote=?,etag=? WHERE item=?',(uuid.uuid4().hex,'',item))
            self.db.execute('DELETE FROM google_conflicts WHERE item=?', (item,))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        self.agenda.invalidate()

    def disconnect(self, account):
        # Keep mappings: reconnecting the same account cannot create duplicates.
        with self.db:
            self.db.execute('UPDATE google_accounts SET connected=0 WHERE id=?', (account,))
        default = self.store.preference('google_default', None)
        if default and default[0] == account:
            self.store.set_preference('google_default', None)


class SyncEngine:
    def __init__(self, store, api, account, cancel=None):
        self.state = GoogleStore(store)
        self.db, self.api, self.account, self.cancel = store.db, api, account, cancel
        self.changed = False

    def check_cancel(self):
        if self.cancel is not None and self.cancel.is_set():
            raise Cancelled()

    def _pull(self, calendar):
        full = not calendar['token']
        try:
            rows, token = self.api.events(calendar['id'], calendar['token'])
        except GoogleError as exc:
            if exc.status != 410:
                raise
            rows, token = self.api.events(calendar['id'], '')
            full = True
        self.check_cancel()
        with self.db:
            if full:
                # Keep tombstones, local outbox and base; never clear user edits.
                seen = {r['id'] for r in rows}
                for old in self.db.execute('SELECT id,payload FROM google_remote WHERE account=? AND calendar=?', (self.account, calendar['id'])).fetchall():
                    if old['id'] not in seen:
                        payload = json.loads(old['payload'])
                        payload['status'] = 'cancelled'
                        self._cache(calendar, payload)
            for row in rows:
                self._cache(calendar, row)
            self.db.execute('UPDATE google_calendars SET token=? WHERE account=? AND id=?', (token, self.account, calendar['id']))

    def _cache(self, calendar, event):
        self.db.execute('INSERT OR REPLACE INTO google_remote VALUES (?,?,?,?)', (self.account, calendar['id'], event['id'], dump(event)))

    def _remote(self, calendar):
        events = [json.loads(row[0]) for row in self.db.execute('SELECT payload FROM google_remote WHERE account=? AND calendar=?', (self.account, calendar['id']))]
        masters = {e['id']: e for e in events if not e.get('recurringEventId')}
        result = {}
        for key, event in masters.items():
            item, readonly = decode(event, calendar['zone'], json.loads(calendar['reminders']))
            result[key] = [item, readonly, event]
        for event in events:
            parent = event.get('recurringEventId')
            if not parent or parent not in result or result[parent][0] is None:
                continue
            item = result[parent][0]
            key, _, _ = read_time(event['originalStartTime'], item['timezone'])
            if event.get('status') == 'cancelled':
                exception = {'cancelled': True}
            else:
                value, readonly = decode(event, item['timezone'], json.loads(calendar['reminders']))
                exception = {'cancelled': False, 'value': {k: v for k, v in value.items() if k not in ('recurrence', 'exceptions')}}
                result[parent][1] |= readonly
            item['exceptions'][key] = exception
        return result

    def run(self):
        for calendar in self.state.calendars(selected=True):
            if calendar['account'] != self.account:
                continue
            self.check_cancel()
            self._pull(calendar)
            remote = self._remote(calendar)
            linked = {r['remote']: dict(r) for r in self.db.execute('SELECT * FROM google_links WHERE account=? AND calendar=?', (self.account, calendar['id']))}
            for key, (value, readonly, event) in remote.items():
                if key not in linked and value is not None:
                    item = uuid.uuid4().hex
                    with self.db:
                        self.db.execute('INSERT INTO google_links (item,account,calendar,remote) VALUES (?,?,?,?)', (item, self.account, calendar['id'], key))
                    linked[key] = self.state.link(item)
            for key, link in linked.items():
                self.check_cancel()
                value, readonly, event = remote.get(key, [None, False, {}])
                self._reconcile(calendar, link, value, readonly, event)
        self.state.agenda.invalidate()
        return self.changed

    def _reconcile(self, calendar, link, remote, readonly, event):
        item = link['item']
        base = json.loads(link['base'])
        self.db.execute('BEGIN IMMEDIATE')
        try:
            local = self.state.snapshot(item)
            # First import has no local item and no acknowledged base.
            value, conflict = merge(base, local, remote)
            readonly = readonly or calendar['role'] not in ('owner', 'writer')
            self.db.execute('UPDATE google_links SET readonly=?,etag=?,url=? WHERE item=?', (readonly, event.get('etag', link['etag']), event.get('htmlLink', link['url']), item))
            if readonly and local != base and local != remote and base is not None:
                conflict = True
            if conflict:
                self.db.execute('INSERT OR REPLACE INTO google_conflicts VALUES (?,?,?)', (item, dump(remote), time.time()))
            else:
                self.db.execute('DELETE FROM google_conflicts WHERE item=?', (item,))
                if value != local:
                    self.state._apply(item, value)
                    self.changed = True
                # Acknowledge the remote state, retaining any pending local delta.
                self.db.execute('UPDATE google_links SET base=? WHERE item=?', (dump(remote), item))
                if value is None and remote is None:
                    self.db.execute('DELETE FROM google_links WHERE item=?', (item,))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        if conflict or readonly or value == remote:
            return
        try:
            acknowledged, result = self._push(calendar, link, value, remote, event)
        except GoogleError as exc:
            if exc.status in (409, 412):
                # No blind retry: the next pull performs another three-way merge.
                return
            raise
        # A GUI edit during HTTP remains pending against the sent snapshot.
        with self.db:
            if result:
                self._cache(calendar, result)
            else:
                self._cache(calendar, {'id': link['remote'], 'status': 'cancelled'})
            self.db.execute('UPDATE google_links SET base=?,etag=? WHERE item=?', (dump(acknowledged), result.get('etag', '') if result else '', item))
            if acknowledged is None and self.state.snapshot(item) is None:
                self.db.execute('DELETE FROM google_links WHERE item=?', (item,))

    def _push(self, calendar, link, local, remote, event):
        cid, rid = calendar['id'], link['remote']
        if local is None:
            try:
                self.api.event(cid, rid, 'DELETE', etag=event.get('etag'))
            except GoogleError as exc:
                if exc.status not in (404, 410):
                    raise
            return None, None
        body = encode(local, remote)
        if remote is None:
            body.update(id=rid, extendedProperties={'private': {'yunJinLink': rid}})
            try:
                result = self.api.event(cid, '', 'POST', body)
            except GoogleError as exc:
                if exc.status != 409:
                    raise
                result = self.api.event(cid, rid)
                if result.get('extendedProperties', {}).get('private', {}).get('yunJinLink') != rid:
                    raise GoogleError(409)
                recovered, _ = decode(result, calendar['zone'], json.loads(calendar['reminders']))
                if any(recovered[k] != local[k] for k in FIELDS):
                    with self.db:
                        self._cache(calendar, result)
                    raise GoogleError(412)
        elif body:
            result = self.api.event(cid, rid, 'PATCH', body, etag=event.get('etag'))
        else:
            result = event
        old_exceptions = (remote or {}).get('exceptions', {})
        for key in sorted(set(local['exceptions']) | set(old_exceptions)):
            exception = local['exceptions'].get(key)
            if exception == old_exceptions.get(key):
                continue
            self.check_cancel()
            original = write_time(key, local['all_day'], local['timezone'])
            # originalStart accepts an RFC3339 timestamp, including all-day anchors.
            original_stamp = original.get('dateTime') or original['date'] + 'T00:00:00Z'
            instance = self.api.instance(cid, rid, original_stamp)
            if exception and exception['cancelled']:
                change = {'status': 'cancelled'}
            else:
                if exception:
                    instance_value = dict(exception['value'], recurrence=None)
                else:
                    duration = datetime.fromisoformat(local['end_local']) - datetime.fromisoformat(local['start_local'])
                    instance_value = dict(local, start_local=key, end_local=(datetime.fromisoformat(key)+duration).isoformat(), recurrence=None)
                change = encode(instance_value)
                change.pop('recurrence', None)
                change['status'] = 'confirmed'
            updated = self.api.event(cid, instance['id'], 'PATCH', change, etag=instance.get('etag'))
            with self.db:
                self._cache(calendar, updated)
        return deepcopy(local), result
