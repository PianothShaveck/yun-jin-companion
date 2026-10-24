"""Real filesystem cleanup, including legacy committed journals and recovery."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_updater import fixture, u


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data'
        self.work = self.data / 'updates/update-legacy'
        self.source = fixture(self.work / 'unpacked/release')
        self.running = fixture(self.root / 'program', '1.1.0',
                               extra={'app/assets/calendar/old.webp': b'old full image'})
        self.app = self.running / 'app'
        self.journal = self.work / 'journal.json'
        u.transaction(self.source, self.app, self.work / 'backup', self.journal)
        self.status('committed')
        u.write_json(self.work / 'plan.json', dict(
            source=str(self.source), app_dir=str(self.app), version='1.2.0',
            lock=str(self.data / 'companion.lock')))
        (self.work / 'release.zip').write_bytes(b'old archive')
        (self.work / 'worker.log').write_text('diagnostics')

    def tearDown(self):
        self.tmp.cleanup()

    def status(self, value):
        doc = json.loads(self.journal.read_text())
        doc['status'] = value
        u.write_json(self.journal, doc)

    def cleanup(self):
        return u.cleanup_completed_updates(self.data, self.app)

    def test_committed_legacy_payloads_removed_without_touching_program_or_unknown_files(self):
        unknown = self.source / 'personal-note.txt'
        unknown.write_text('keep')
        backup_unknown = self.work / 'backup/private.txt'
        backup_unknown.write_text('keep too')
        before = {str(p): p.read_bytes() for p in self.running.rglob('*') if p.is_file()}
        self.assertGreater(self.cleanup(), 0)
        self.assertFalse((self.work / 'release.zip').exists())
        self.assertFalse((self.source / 'app').exists())
        self.assertFalse((self.work / 'backup/app').exists())
        self.assertEqual(unknown.read_text(), 'keep')
        self.assertEqual(backup_unknown.read_text(), 'keep too')
        self.assertEqual((self.work / 'worker.log').read_text(), 'diagnostics')
        self.assertTrue(self.journal.is_file())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.running.rglob('*') if p.is_file()})
        self.assertEqual(self.cleanup(), 0)

    def test_unconfirmed_or_active_updates_keep_rollback_payload(self):
        for status in ('applying', 'installed', 'rolled_back'):
            self.status(status)
            self.assertEqual(self.cleanup(), 0)
            self.assertTrue((self.work / 'backup/app/assets/calendar/old.webp').is_file())
        self.status('committed')
        pending = self.data / 'updates/pending.json'
        u.write_json(pending, {'work': str(self.work)})
        self.assertEqual(self.cleanup(), 0)
        pending.write_text('{broken')
        self.assertEqual(self.cleanup(), 0)
        self.assertTrue((self.work / 'release.zip').is_file())

    def test_foreign_destination_and_unsafe_journal_are_ignored(self):
        self.assertEqual(u.cleanup_completed_updates(self.data, self.root / 'other/app'), 0)
        doc = json.loads(self.journal.read_text())
        doc['entries'].append({'name': '../private.txt', 'existed': True})
        u.write_json(self.journal, doc)
        self.assertEqual(self.cleanup(), 0)
        self.assertTrue((self.work / 'release.zip').is_file())

    def test_symlink_backup_never_traversed(self):
        backup = self.work / 'backup'
        outside = self.root / 'outside'
        shutil.move(backup, outside)
        try:
            backup.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Symlinks unavailable')
        self.cleanup()
        self.assertTrue((outside / 'app/assets/calendar/old.webp').is_file())
        self.assertTrue(backup.is_symlink())

    def test_locked_source_file_can_be_retried(self):
        locked = self.source / 'app/yun_jin_app.py'
        real_unlink = Path.unlink
        def unlink(path, *args, **kwargs):
            if path == locked:
                raise PermissionError('open Windows file')
            return real_unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', unlink):
            self.cleanup()
        self.assertTrue(locked.is_file())
        self.assertTrue((self.source / 'app' / u.MANIFEST).is_file())
        self.assertGreater(self.cleanup(), 0)
        self.assertFalse(self.source.exists())


if __name__ == '__main__':
    unittest.main()
