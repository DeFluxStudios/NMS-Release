import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    author TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'valid',
    message_id INTEGER,
    channel_id INTEGER,
    ai_score REAL,
    final_score REAL,
    reason TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS winners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week TEXT NOT NULL,
    entry_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    url TEXT NOT NULL,
    reason TEXT,
    state TEXT NOT NULL,
    publish_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS optouts (user_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    def _one(self, sql, args=()):
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _all(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _run(self, sql, args=()):
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur

    def get_setting(self, key, default=None):
        row = self._one('SELECT value FROM settings WHERE key=?', (key,))
        return row['value'] if row else default

    def set_setting(self, key, value):
        self._run('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                  (key, str(value)))

    def is_paused(self):
        return self.get_setting('paused', '0') == '1'

    def add_optout(self, user_id):
        self._run('INSERT OR IGNORE INTO optouts(user_id) VALUES(?)', (user_id,))

    def remove_optout(self, user_id):
        self._run('DELETE FROM optouts WHERE user_id=?', (user_id,))

    def is_optout(self, user_id):
        return self._one('SELECT 1 AS x FROM optouts WHERE user_id=?', (user_id,)) is not None

    def add_entry(self, week, user_id, author, title, url, description):
        cur = self._run(
            'INSERT INTO entries(week,user_id,author,title,url,description,created_at) VALUES(?,?,?,?,?,?,?)',
            (week, user_id, author, title, url, description, now_iso()))
        return cur.lastrowid

    def set_entry_message(self, entry_id, channel_id, message_id):
        self._run('UPDATE entries SET channel_id=?, message_id=? WHERE id=?', (channel_id, message_id, entry_id))

    def get_entry(self, entry_id):
        return self._one('SELECT * FROM entries WHERE id=?', (entry_id,))

    def set_entry_status(self, entry_id, status):
        self._run('UPDATE entries SET status=? WHERE id=?', (status, entry_id))

    def set_entry_score(self, entry_id, ai_score, final_score, reason):
        self._run('UPDATE entries SET ai_score=?, final_score=?, reason=? WHERE id=?',
                  (ai_score, final_score, reason, entry_id))

    def count_user_week(self, user_id, week):
        row = self._one("SELECT COUNT(*) AS n FROM entries WHERE user_id=? AND week=? AND status!='withdrawn'",
                        (user_id, week))
        return row['n']

    def url_used(self, url):
        return self._one("SELECT 1 AS x FROM entries WHERE url=? AND status!='withdrawn'", (url,)) is not None

    def valid_entries(self, week):
        return self._all("SELECT * FROM entries WHERE week=? AND status='valid' ORDER BY id", (week,))

    def user_entries(self, user_id, week):
        return self._all("SELECT * FROM entries WHERE user_id=? AND week=? AND status!='withdrawn' ORDER BY id",
                         (user_id, week))

    def withdraw_entry(self, entry_id, user_id):
        cur = self._run("UPDATE entries SET status='withdrawn' WHERE id=? AND user_id=? AND status='valid'",
                        (entry_id, user_id))
        return cur.rowcount > 0

    def remove_user_entries(self, user_id):
        self._run("UPDATE entries SET status='withdrawn' WHERE user_id=? AND status='valid'", (user_id,))

    def add_winner(self, week, entry, reason, publish_at):
        cur = self._run(
            'INSERT INTO winners(week,entry_id,title,author,url,reason,state,publish_at,created_at) '
            "VALUES(?,?,?,?,?,?,'pending',?,?)",
            (week, entry['id'], entry['title'], entry['author'], entry['url'], reason, publish_at, now_iso()))
        return cur.lastrowid

    def pending_winner(self):
        return self._one("SELECT * FROM winners WHERE state='pending' ORDER BY id DESC LIMIT 1")

    def live_winner(self):
        return self._one("SELECT * FROM winners WHERE state='live' ORDER BY id DESC LIMIT 1")

    def set_winner_state(self, winner_id, state):
        self._run('UPDATE winners SET state=? WHERE id=?', (state, winner_id))

    def retire_live(self):
        self._run("UPDATE winners SET state='past' WHERE state='live'")

    def week_has_winner(self, week):
        return self._one('SELECT 1 AS x FROM winners WHERE week=?', (week,)) is not None
