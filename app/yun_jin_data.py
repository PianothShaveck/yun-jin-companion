# SPDX-License-Identifier: GPL-3.0-or-later
"""Local persistent storage. All timestamps are UTC Unix seconds."""
import json
import os
import sqlite3
import sys
import time
import uuid
import zipfile
from pathlib import Path


def data_directory():
    override = os.environ.get('YUNJIN_DATA_DIR')
    if override:
        root = Path(override)
    elif sys.platform == 'win32':
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'YunJinPet'
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library/Application Support/YunJinPet'
    else:
        root = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'YunJinPet'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'attachments').mkdir(exist_ok=True)
    return root


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'attachments').mkdir(exist_ok=True)
        self.db = sqlite3.connect(str(self.root / 'companion.sqlite3'), timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
                path TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, due REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL,
                completed REAL);
            CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS reminder_due ON reminders(status,due);
        ''')

    def preference(self, key, default):
        r = self.db.execute('SELECT value FROM preferences WHERE key=?', (key,)).fetchone()
        return json.loads(r[0]) if r else default

    def set_preference(self, key, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO preferences VALUES (?,?)', (key, json.dumps(value)))

    def save_note(self, title, body, path='', note_id=None):
        now = time.time()
        title = title.strip() or (body.strip().splitlines() or ['Appunto'])[0][:90]
        if note_id:
            with self.db:
                cur = self.db.execute('UPDATE notes SET title=?,body=?,path=?,updated=? WHERE id=?',
                                     (title, body, path, now, note_id))
                if cur.rowcount != 1:
                    raise ValueError('Appunto non trovato; il testo resta nell’editor.')
        else:
            note_id = uuid.uuid4().hex
            with self.db:
                self.db.execute('INSERT INTO notes VALUES (?,?,?,?,?,?)',
                                (note_id, title, body, path, now, now))
        return note_id

    def notes(self, query=''):
        # instr treats search input literally, including %, _ and backslashes.
        return [dict(r) for r in self.db.execute('''SELECT * FROM notes
            WHERE instr(lower(title || char(10) || body || char(10) || path),lower(?))>0
            ORDER BY updated DESC''', (query,))]

    def note(self, note_id):
        r = self.db.execute('SELECT * FROM notes WHERE id=?', (note_id,)).fetchone()
        return dict(r) if r else None

    def delete_note(self, note_id):
        with self.db:
            self.db.execute('DELETE FROM notes WHERE id=?', (note_id,))
        # Attachments are kept for recovery; deletion of a shortcut never deletes its target.

    def add_reminder(self, title, due, reminder_id=None):
        if not title.strip():
            raise ValueError('Scrivi cosa vuoi ricordare.')
        if not isinstance(due, (int, float)) or not 0 < due < 32503680000:
            raise ValueError('Data non valida.')
        with self.db:
            if reminder_id:
                cur = self.db.execute("UPDATE reminders SET title=?,due=?,status='pending',completed=NULL WHERE id=?",
                                     (title.strip(), due, reminder_id))
                if cur.rowcount != 1:
                    raise ValueError('Promemoria non trovato.')
            else:
                reminder_id = uuid.uuid4().hex
                self.db.execute('INSERT INTO reminders VALUES (?,?,?,?,?,NULL)',
                                (reminder_id, title.strip(), due, 'pending', time.time()))
        return reminder_id

    def reminders(self, include_done=False):
        sql = 'SELECT * FROM reminders'
        if not include_done:
            sql += " WHERE status!='done'"
        return [dict(r) for r in self.db.execute(sql + ' ORDER BY due')]

    def mark_due(self, now=None):
        now = time.time() if now is None else now
        with self.db:
            self.db.execute("UPDATE reminders SET status='due' WHERE status='pending' AND due<=?", (now,))
        return [dict(r) for r in self.db.execute("SELECT * FROM reminders WHERE status='due' ORDER BY due")]

    def complete(self, reminder_id):
        with self.db:
            self.db.execute("UPDATE reminders SET status='done',completed=? WHERE id=?", (time.time(), reminder_id))

    def snooze(self, reminder_id, minutes=10):
        with self.db:
            self.db.execute("UPDATE reminders SET status='pending',due=?,completed=NULL WHERE id=?",
                            (time.time() + minutes*60, reminder_id))

    def delete_reminder(self, reminder_id):
        with self.db:
            self.db.execute('DELETE FROM reminders WHERE id=?', (reminder_id,))

    def export_backup(self, destination):
        """Consistent SQLite snapshot, readable JSON, and captured images.
        Linked external files are NOT copied; their paths are in notes.json.
        """
        tmp = self.root / ('backup-' + uuid.uuid4().hex + '.sqlite3')
        out = Path(destination)
        stage = out.with_name(out.name + '.part')
        try:
            with sqlite3.connect(str(tmp)) as target:
                self.db.backup(target)
            with zipfile.ZipFile(stage, 'w', zipfile.ZIP_DEFLATED) as z:
                z.write(tmp, 'companion.sqlite3')
                z.writestr('notes.json', json.dumps(self.notes(), ensure_ascii=False, indent=2))
                z.writestr('reminders.json', json.dumps(self.reminders(True), ensure_ascii=False, indent=2))
                for image in sorted((self.root/'attachments').glob('*.png')):
                    z.write(image, 'attachments/' + image.name)
            os.replace(stage, out)
        finally:
            tmp.unlink(missing_ok=True)
            stage.unlink(missing_ok=True)

    def close(self):
        self.db.close()
