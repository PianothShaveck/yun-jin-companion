"""Independent SQLite profiles sharing a strict Calendar-like server."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from yun_jin_data import Store
from yun_jin_google_calendar import SyncEngine
from yun_jin_google_auth import GoogleError
from yun_jin_google_codec import read_time, write_time


class Server:
    def __init__(self):
        self.rows, self.clock, self.writes = {}, 0, 0
        self.lose_response = False
        self.expired = False
        self.before_write = None

    def events(self, calendar, token=''):
        if self.expired and token:
            self.expired = False
            raise GoogleError(410)
        return copy.deepcopy(list(self.rows.values())), str(self.clock)

    def event(self, calendar, remote, method='GET', data=None, etag=None):
        if method == 'GET':
            if remote not in self.rows:
                raise GoogleError(404)
            return copy.deepcopy(self.rows[remote])
        if self.before_write:
            callback, self.before_write = self.before_write, None
            callback()
        if method == 'POST':
            remote = data['id']
            if remote in self.rows:
                raise GoogleError(409)
            row = copy.deepcopy(data)
        else:
            if remote not in self.rows:
                raise GoogleError(404)
            if self.rows[remote]['etag'] != etag:
                raise GoogleError(412)
            row = copy.deepcopy(self.rows[remote])
            row.update(copy.deepcopy(data or {}))
            if method == 'DELETE':
                row['status'] = 'cancelled'
        self.clock += 1
        self.writes += 1
        row.update(id=remote, etag='"'+str(self.clock)+'"')
        self.rows[remote] = row
        if self.lose_response:
            self.lose_response = False
            raise GoogleError()
        return copy.deepcopy(row) if method != 'DELETE' else {}

    def instance(self, calendar, remote, original):
        for row in self.rows.values():
            value = row.get('originalStartTime', {})
            if row.get('recurringEventId') == remote and (value.get('dateTime') == original or value.get('date') == original[:10]):
                return copy.deepcopy(row)
        parent = self.rows[remote]
        rid = remote + '_' + original
        row = copy.deepcopy(parent)
        row.pop('recurrence', None)
        row.update(id=rid, recurringEventId=remote, originalStartTime={'dateTime':original})
        self.rows[rid] = row
        return copy.deepcopy(row)


class MultiDeviceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stores = [Store(Path(self.tmp.name)/str(i)) for i in range(2)]
        self.server = Server()
        for s in self.stores:
            s.google.account('account', 'person@example.test')
            s.google.set_calendars('account', [dict(id='calendar', summary='Test', accessRole='owner', timeZone='Europe/Rome')])
            s.google.select('account', 'calendar', True)
        self.a, self.b = self.stores

    def tearDown(self):
        for store in self.stores:
            store.close()
        self.tmp.cleanup()

    def sync(self, store):
        return SyncEngine(store, self.server, 'account').run()

    def create(self, store=None, **extra):
        store = store or self.a
        options = dict(title='Lesson', start='2027-01-15T10:00:00', end='2027-01-15T11:00:00', timezone='Europe/Rome', reminder_minutes=10)
        options.update(extra)
        item = store.agenda.save_event(**options)
        store.google.assign(item, 'account', 'calendar')
        return item

    def edit(self, store, item, **changes):
        value = store.agenda.get(item)
        fields = dict(title=value['title'], start=value['start_local'], end=value['end_local'],
            all_day=value['all_day'], recurrence=value['recurrence'], reminder_minutes=value['reminder_minutes'],
            voice=value['voice'], details=value['details'], timezone=value['timezone'], color=value['color'], event_id=item)
        fields.update(changes)
        store.agenda.save_event(**fields)

    def setup_pair(self, **extra):
        first = self.create(**extra)
        self.sync(self.a)
        self.sync(self.b)
        return first, self.b.agenda.events()[0]['id']

    def test_create_edit_delete_both_directions_and_no_repeat_writes(self):
        first, second = self.setup_pair()
        self.edit(self.b, second, title='Changed')
        self.sync(self.b); self.sync(self.a)
        self.assertEqual(self.a.agenda.get(first)['title'], 'Changed')
        writes = self.server.writes
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(self.server.writes, writes)
        self.a.agenda.delete(first)
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(self.b.agenda.events(), [])
        self.assertEqual(self.a.google.conflicts(), [])

    def test_offline_edits_different_fields_merge(self):
        first, second = self.setup_pair()
        self.edit(self.a, first, title='From Mac')
        self.edit(self.b, second, details='From Windows')
        self.sync(self.b); self.sync(self.a); self.sync(self.b)
        for store in self.stores:
            value = store.agenda.events()[0]
            self.assertEqual(value['title'], 'From Mac')
            self.assertEqual(value['details'], 'From Windows')
        writes = self.server.writes
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(writes, self.server.writes)

    def test_conflict_keep_both_preserves_local_copy_without_upload(self):
        first, second = self.setup_pair()
        self.edit(self.a, first, title='Local')
        self.edit(self.b, second, title='Remote')
        self.sync(self.b); self.sync(self.a)
        self.assertEqual(len(self.a.google.conflicts()), 1)
        self.a.google.resolve(first, 'both')
        self.sync(self.a); self.sync(self.b)
        self.assertEqual({e['title'] for e in self.a.agenda.events()}, {'Local', 'Remote'})
        self.assertEqual([e['title'] for e in self.b.agenda.events()], ['Remote'])
        self.assertEqual(len(self.server.rows), 1)

    def test_lost_insert_response_and_restart_do_not_duplicate(self):
        item = self.create()
        self.server.lose_response = True
        with self.assertRaises(GoogleError): self.sync(self.a)
        root = self.a.root
        self.a.close()
        self.a = self.stores[0] = Store(root)
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(len(self.server.rows), 1)
        self.assertEqual(len(self.a.agenda.events()), 1)
        self.assertEqual(len(self.b.agenda.events()), 1)
        self.assertFalse(self.a.google.conflicts())
        self.assertEqual(self.server.writes, 1)

    def test_local_only_never_uploads(self):
        self.a.agenda.save_event('Private', '2027-02-01T12:00:00')
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(self.server.rows, {})
        self.assertEqual(self.b.agenda.events(), [])

    def test_multiday_and_moved_cancelled_recurrences(self):
        first, second = self.setup_pair(recurrence={'frequency':'daily','count':3})
        self.a.agenda.save_exception(first, '2027-01-16T10:00:00', start_local='2027-01-16T12:00:00', end_local='2027-01-16T13:00:00')
        self.a.agenda.skip_occurrence(first, '2027-01-17T10:00:00')
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(self.a.google.snapshot(first), self.b.google.snapshot(second))
        self.assertEqual(len(self.b.google.snapshot(second)['exceptions']), 2)
        self.create(self.b, title='Trip', start='2027-02-01', end='2027-02-03', all_day=True)
        self.sync(self.b); self.sync(self.a)
        trip = next(e for e in self.a.agenda.events() if e['title']=='Trip')
        self.assertEqual(trip['end_local'], '2027-02-03T00:00:00')
        self.assertTrue(trip['all_day'])

    def test_expired_token_preserves_pending_edits_and_handles_remote_delete(self):
        first, second = self.setup_pair()
        self.edit(self.a, first, details='Offline')
        self.server.expired = True
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(self.b.agenda.get(second)['details'], 'Offline')
        self.b.agenda.delete(second); self.sync(self.b)
        self.server.expired = True
        self.sync(self.a)
        self.assertEqual(self.a.agenda.events(), [])

    def test_gui_edit_during_network_is_still_pending(self):
        first, second = self.setup_pair()
        self.edit(self.a, first, title='First edit')
        self.server.before_write = lambda:self.edit(self.a, first, title='Later edit')
        self.sync(self.a)
        self.assertEqual(self.a.agenda.get(first)['title'], 'Later edit')
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(self.b.agenda.get(second)['title'], 'Later edit')

    def test_precondition_failure_does_not_overwrite_remote(self):
        first, second = self.setup_pair()
        self.edit(self.a, first, title='Local')
        rid = self.a.google.link(first)['remote']
        def race():
            self.server.rows[rid]['summary']='Remote race'
            self.server.rows[rid]['etag']='"concurrent"'
        self.server.before_write = race
        self.sync(self.a); self.sync(self.a)
        self.assertEqual(self.server.rows[rid]['summary'], 'Remote race')
        self.assertEqual(len(self.a.google.conflicts()), 1)

    def test_readonly_and_unsupported_recurrence_preserved(self):
        first, second = self.setup_pair()
        rid = self.a.google.link(first)['remote']
        self.server.rows[rid]['recurrence']=['RRULE:FREQ=MONTHLY;BYDAY=2MO']
        self.server.rows[rid]['location']='Keep this location'
        self.sync(self.b)
        self.assertTrue(self.b.google.readonly(second))
        self.assertEqual(self.server.rows[rid]['recurrence'], ['RRULE:FREQ=MONTHLY;BYDAY=2MO'])
        self.assertEqual(self.server.rows[rid]['location'], 'Keep this location')

    def test_disconnect_reconnect_and_backup_are_detached(self):
        first, second = self.setup_pair()
        self.a.google.disconnect('account')
        self.edit(self.a, first, title='Preserved')
        writes = self.server.writes
        self.sync(self.a)
        self.assertEqual(writes, self.server.writes)
        self.a.google.account('account', 'person@example.test')
        self.sync(self.a); self.sync(self.b)
        self.assertEqual(self.b.agenda.get(second)['title'], 'Preserved')
        backup = Path(self.tmp.name)/'backup.zip'
        self.a.export_backup(backup)
        with zipfile.ZipFile(backup) as z:
            z.extract('companion.sqlite3', Path(self.tmp.name)/'restored')
        restored = Store(Path(self.tmp.name)/'restored')
        try:
            self.assertEqual(len(restored.agenda.events()), 1)
            self.assertEqual(restored.google.calendars(), [])
            self.assertNotEqual(restored.preference('google_profile', ''), self.a.preference('google_profile', ''))
        finally: restored.close()

    def test_resolve_remote_deletion_with_local_recreates_new_id(self):
        first, second = self.setup_pair()
        self.edit(self.a, first, title='Keep')
        self.b.agenda.delete(second); self.sync(self.b); self.sync(self.a)
        old = self.a.google.link(first)['remote']
        self.a.google.resolve(first, 'local')
        self.sync(self.a); self.sync(self.b)
        self.assertNotEqual(self.a.google.link(first)['remote'], old)
        self.assertEqual([e['title'] for e in self.b.agenda.events()], ['Keep'])


if __name__ == '__main__':
    unittest.main()
