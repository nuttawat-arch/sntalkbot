# -*- coding: utf-8 -*-
"""Persistent runtime state for SNTalkBot.

SQLite is the canonical store for state that must survive process/container
restart. High-frequency realtime TeamTalk/media state intentionally remains in
memory and is exposed through the loopback API instead of being written here.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections.abc import MutableSequence, Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 3
_QUEUE_GAP = 1024

_SCHEMA_SQL = r"""
                CREATE TABLE IF NOT EXISTS state_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS queue_entries (
                    seq INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    link TEXT NOT NULL UNIQUE,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_key TEXT NOT NULL,
                    target_type TEXT NOT NULL CHECK(target_type IN ('nickname','username')),
                    target_value TEXT NOT NULL,
                    telegram_chat_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(owner_key, target_type, target_value, telegram_chat_id)
                );
                CREATE INDEX IF NOT EXISTS idx_notifications_target
                    ON notifications(target_type, target_value);
                CREATE TABLE IF NOT EXISTS offline_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_username TEXT NOT NULL,
                    sender_username TEXT NOT NULL,
                    sender_nickname TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_offline_messages_target
                    ON offline_messages(target_username, id);
                CREATE TABLE IF NOT EXISTS account_registry (
                    username TEXT PRIMARY KEY,
                    telegram_chat_id TEXT,
                    ip_hash TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_account_registry_chat
                    ON account_registry(telegram_chat_id);
                CREATE INDEX IF NOT EXISTS idx_account_registry_ip
                    ON account_registry(ip_hash);
                CREATE TABLE IF NOT EXISTS moderation_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL CHECK(action IN ('kick','ban')),
                    subject_type TEXT NOT NULL CHECK(subject_type IN ('nickname','username','ip')),
                    subject_value TEXT NOT NULL,
                    ban_type INTEGER NOT NULL DEFAULT 0,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(action, subject_type, subject_value)
                );
                CREATE INDEX IF NOT EXISTS idx_moderation_expiry
                    ON moderation_rules(expires_at);
                CREATE TABLE IF NOT EXISTS scheduled_deletions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_path TEXT NOT NULL,
                    channel_id INTEGER NOT NULL,
                    remote_name TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(local_path, channel_id, remote_name)
                );
                CREATE INDEX IF NOT EXISTS idx_deletion_expiry
                    ON scheduled_deletions(expires_at);
                CREATE TABLE IF NOT EXISTS private_channels (
                    channel_key TEXT PRIMARY KEY,
                    user_a TEXT NOT NULL,
                    user_b TEXT NOT NULL,
                    channel_name TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_key TEXT NOT NULL,
                    pref_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_key, pref_key)
                );
                CREATE TABLE IF NOT EXISTS update_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """



class StateStore:
    def __init__(self, path: str | os.PathLike | None = None):
        data_dir = Path(os.getenv("TTUTIL_DATA_DIR", "."))
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = Path(path) if path else data_dir / "state.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = None
        try:
            self._conn = sqlite3.connect(
                str(self.path), timeout=10.0, check_same_thread=False, isolation_level=None
            )
            self._conn.row_factory = sqlite3.Row
            with self._lock:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._conn.execute("PRAGMA foreign_keys=ON")
                self._conn.execute("PRAGMA busy_timeout=10000")
            self._migrate()
        except Exception:
            # Windows keeps SQLite database/WAL files locked while a connection is
            # open.  Constructor failures (for example a newer unsupported schema)
            # must therefore release the handle deterministically before re-raising.
            conn = self._conn
            self._conn = None
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            raise

    def close(self):
        with self._lock:
            conn = self._conn
            if conn is None:
                return
            self._conn = None
            try:
                try:
                    conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except sqlite3.Error:
                    pass
            finally:
                conn.close()

    @contextmanager
    def transaction(self):
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def _migrate(self):
        with self._lock:
            version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"state.sqlite3 schema {version} is newer than this SNTalkBot "
                    f"supports ({SCHEMA_VERSION}); refusing unsafe downgrade"
                )
            # sqlite3.executescript() manages transaction boundaries itself.
            # Put BEGIN/COMMIT inside the script so schema creation + version
            # bump are genuinely atomic even with isolation_level=None.
            migration_sql = "BEGIN IMMEDIATE;\n" + _SCHEMA_SQL + f"\nPRAGMA user_version={SCHEMA_VERSION};\nCOMMIT;"
            try:
                self._conn.executescript(migration_sql)
            except Exception:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    # ---------- generic metadata ----------
    def get_meta(self, key, default=None):
        with self._lock:
            row = self._conn.execute("SELECT value FROM state_meta WHERE key=?", (str(key),)).fetchone()
        return default if row is None else row[0]

    def set_meta(self, key, value):
        with self._lock:
            self._conn.execute(
                "INSERT INTO state_meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), str(value)),
            )

    def delete_meta(self, key):
        with self._lock:
            self._conn.execute("DELETE FROM state_meta WHERE key=?", (str(key),))

    # ---------- queue ----------
    def queue(self):
        return PersistentQueue(self)

    def queue_count(self):
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM queue_entries").fetchone()[0])

    def queue_page(self, *, after_seq=None, limit=500):
        limit = max(1, min(int(limit or 500), 5000))
        with self._lock:
            if after_seq is None:
                rows = self._conn.execute(
                    "SELECT seq,payload FROM queue_entries ORDER BY seq LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT seq,payload FROM queue_entries WHERE seq>? ORDER BY seq LIMIT ?",
                    (int(after_seq), limit),
                ).fetchall()
        items = []
        last_seq = None
        for row in rows:
            last_seq = int(row["seq"])
            try:
                items.append(json.loads(row["payload"]))
            except Exception:
                items.append({"title": "Corrupt queue item", "link": ""})
        return items, last_seq

    def replace_queue(self, items):
        serialized = [json.dumps(dict(item), ensure_ascii=False, separators=(",", ":")) for item in items]
        with self.transaction() as db:
            db.execute("DELETE FROM queue_entries")
            db.executemany(
                "INSERT INTO queue_entries(seq,payload) VALUES(?,?)",
                [((idx + 1) * _QUEUE_GAP, payload) for idx, payload in enumerate(serialized)],
            )

    # ---------- favorites ----------
    def load_favorites(self):
        with self._lock:
            rows = self._conn.execute("SELECT payload FROM favorites ORDER BY id").fetchall()
        result = []
        for row in rows:
            try:
                result.append(json.loads(row[0]))
            except Exception:
                continue
        return result

    def save_favorites(self, items):
        now = time.time()
        with self.transaction() as db:
            db.execute("DELETE FROM favorites")
            for item in items or []:
                link = str((item or {}).get("link") or "").strip()
                if not link:
                    continue
                db.execute(
                    "INSERT OR REPLACE INTO favorites(link,payload,created_at) VALUES(?,?,?)",
                    (link, json.dumps(dict(item), ensure_ascii=False, separators=(",", ":")), now),
                )

    # ---------- notification subscriptions ----------
    @staticmethod
    def normalize_key(value):
        return str(value or "").strip().casefold()

    def add_notification(self, owner_key, target_type, target_value, chat_id):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO notifications(owner_key,target_type,target_value,telegram_chat_id,created_at) "
                "VALUES(?,?,?,?,?)",
                (self.normalize_key(owner_key), target_type, self.normalize_key(target_value), str(chat_id).strip(), time.time()),
            )

    def remove_notification(self, owner_key, target_type, target_value, chat_id=None):
        params = [self.normalize_key(owner_key), target_type, self.normalize_key(target_value)]
        sql = "DELETE FROM notifications WHERE owner_key=? AND target_type=? AND target_value=?"
        if chat_id is not None:
            sql += " AND telegram_chat_id=?"
            params.append(str(chat_id).strip())
        with self._lock:
            cur = self._conn.execute(sql, params)
        return cur.rowcount

    def pop_notifications_for(self, target_type, target_value):
        value = self.normalize_key(target_value)
        with self.transaction() as db:
            rows = db.execute(
                "SELECT id,owner_key,telegram_chat_id FROM notifications WHERE target_type=? AND target_value=? ORDER BY id",
                (target_type, value),
            ).fetchall()
            if rows:
                db.executemany("DELETE FROM notifications WHERE id=?", [(row["id"],) for row in rows])
        return [dict(row) for row in rows]

    # ---------- offline messages ----------
    def add_offline_message(self, target_username, sender_username, sender_nickname, message):
        with self._lock:
            self._conn.execute(
                "INSERT INTO offline_messages(target_username,sender_username,sender_nickname,message,created_at) VALUES(?,?,?,?,?)",
                (
                    self.normalize_key(target_username),
                    str(sender_username or ""),
                    str(sender_nickname or ""),
                    str(message or ""),
                    time.time(),
                ),
            )

    def pop_offline_messages(self, target_username):
        target = self.normalize_key(target_username)
        with self.transaction() as db:
            rows = db.execute(
                "SELECT id,sender_username,sender_nickname,message,created_at FROM offline_messages "
                "WHERE target_username=? ORDER BY id",
                (target,),
            ).fetchall()
            if rows:
                db.executemany("DELETE FROM offline_messages WHERE id=?", [(row["id"],) for row in rows])
        return [dict(row) for row in rows]

    def sent_offline_messages(self, sender_username):
        with self._lock:
            rows = self._conn.execute(
                "SELECT target_username,message,created_at FROM offline_messages WHERE lower(sender_username)=? ORDER BY id",
                (self.normalize_key(sender_username),),
            ).fetchall()
        return [dict(row) for row in rows]

    # ---------- account registry ----------
    @staticmethod
    def ip_fingerprint(ip_address):
        value = str(ip_address or "").strip().encode("utf-8", "replace")
        return hashlib.sha256(value).hexdigest() if value else None

    def account_exists(self, *, username=None, telegram_chat_id=None, ip_address=None):
        clauses, params = [], []
        if username:
            clauses.append("username=?")
            params.append(self.normalize_key(username))
        if telegram_chat_id:
            clauses.append("telegram_chat_id=?")
            params.append(str(telegram_chat_id).strip())
        if ip_address:
            clauses.append("ip_hash=?")
            params.append(self.ip_fingerprint(ip_address))
        if not clauses:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM account_registry WHERE " + " OR ".join(clauses) + " LIMIT 1", params
            ).fetchone()
        return row is not None

    def record_account(self, username, telegram_chat_id=None, ip_address=None):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO account_registry(username,telegram_chat_id,ip_hash,created_at) VALUES(?,?,?,?)",
                (
                    self.normalize_key(username),
                    str(telegram_chat_id).strip() if telegram_chat_id else None,
                    self.ip_fingerprint(ip_address),
                    time.time(),
                ),
            )

    # ---------- timed moderation ----------
    def upsert_moderation(self, action, subject_type, subject_value, expires_at, ban_type=0):
        with self._lock:
            self._conn.execute(
                "INSERT INTO moderation_rules(action,subject_type,subject_value,ban_type,expires_at,created_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(action,subject_type,subject_value) DO UPDATE SET "
                "ban_type=excluded.ban_type, expires_at=excluded.expires_at, created_at=excluded.created_at",
                (action, subject_type, self.normalize_key(subject_value), int(ban_type or 0), float(expires_at), time.time()),
            )

    def active_moderation(self, now=None):
        """Return active rules without deleting expired rows.

        Expired ban rows must remain visible to the scheduler until the matching
        TeamTalk server-side ban has been removed. Deleting them during a login
        check could otherwise leave a permanent server ban behind.
        """
        now = time.time() if now is None else float(now)
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,action,subject_type,subject_value,ban_type,expires_at "
                "FROM moderation_rules WHERE expires_at>? ORDER BY expires_at",
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def expired_moderation(self, now=None):
        now = time.time() if now is None else float(now)
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,action,subject_type,subject_value,ban_type,expires_at "
                "FROM moderation_rules WHERE expires_at<=? ORDER BY expires_at,id",
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_moderation(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,action,subject_type,subject_value,ban_type,expires_at "
                "FROM moderation_rules ORDER BY expires_at,id"
            ).fetchall()
        return [dict(row) for row in rows]

    def next_moderation_expiry(self):
        with self._lock:
            row = self._conn.execute("SELECT MIN(expires_at) FROM moderation_rules").fetchone()
        return None if row is None or row[0] is None else float(row[0])

    def matching_moderation(self, *, nickname="", username="", ip_address="", now=None):
        values = {
            "nickname": self.normalize_key(nickname),
            "username": self.normalize_key(username),
            "ip": self.normalize_key(ip_address),
        }
        return [
            row for row in self.active_moderation(now)
            if values.get(row["subject_type"]) == row["subject_value"]
        ]

    def clear_moderation(self, target=None):
        with self._lock:
            if target is None:
                cur = self._conn.execute("DELETE FROM moderation_rules")
            else:
                cur = self._conn.execute(
                    "DELETE FROM moderation_rules WHERE subject_value=?", (self.normalize_key(target),)
                )
        return cur.rowcount

    def expired_bans(self, now=None):
        now = time.time() if now is None else float(now)
        with self._lock:
            rows = self._conn.execute(
                "SELECT id,subject_type,subject_value,ban_type FROM moderation_rules "
                "WHERE action='ban' AND expires_at<=? ORDER BY id",
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_moderation_ids(self, ids):
        ids = [int(v) for v in ids]
        if not ids:
            return
        with self._lock:
            self._conn.executemany("DELETE FROM moderation_rules WHERE id=?", [(v,) for v in ids])

    # ---------- scheduled file deletion ----------
    def schedule_deletion(self, local_path, channel_id, remote_name, expires_at):
        with self._lock:
            self._conn.execute(
                "INSERT INTO scheduled_deletions(local_path,channel_id,remote_name,expires_at,created_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(local_path,channel_id,remote_name) DO UPDATE SET expires_at=excluded.expires_at",
                (str(local_path), int(channel_id), str(remote_name), float(expires_at), time.time()),
            )

    def due_deletions(self, now=None, limit=100):
        now = time.time() if now is None else float(now)
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM scheduled_deletions WHERE expires_at<=? ORDER BY expires_at LIMIT ?",
                (now, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def next_deletion_time(self):
        with self._lock:
            row = self._conn.execute("SELECT MIN(expires_at) FROM scheduled_deletions").fetchone()
        return None if row is None or row[0] is None else float(row[0])

    def reschedule_deletion(self, row_id, expires_at):
        with self._lock:
            self._conn.execute(
                "UPDATE scheduled_deletions SET expires_at=? WHERE id=?",
                (float(expires_at), int(row_id)),
            )

    def delete_deletion(self, row_id):
        with self._lock:
            self._conn.execute("DELETE FROM scheduled_deletions WHERE id=?", (int(row_id),))

    # ---------- private channels ----------
    def save_private_channel(self, user_a, user_b, channel_name):
        users = sorted([self.normalize_key(user_a), self.normalize_key(user_b)])
        key = "\x1f".join(users)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO private_channels(channel_key,user_a,user_b,channel_name,created_at) VALUES(?,?,?,?,?)",
                (key, users[0], users[1], str(channel_name), time.time()),
            )
        return key

    def list_private_channels(self):
        with self._lock:
            rows = self._conn.execute("SELECT * FROM private_channels ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]

    def delete_private_channel(self, channel_key):
        with self._lock:
            self._conn.execute("DELETE FROM private_channels WHERE channel_key=?", (str(channel_key),))

    # ---------- user preferences ----------
    def get_preferences(self, user_key):
        with self._lock:
            rows = self._conn.execute(
                "SELECT pref_key,value_json FROM user_preferences WHERE user_key=?",
                (str(user_key),),
            ).fetchall()
        result = {}
        for row in rows:
            try:
                result[row["pref_key"]] = json.loads(row["value_json"])
            except Exception:
                pass
        return result

    def set_preference(self, user_key, pref_key, value):
        with self._lock:
            self._conn.execute(
                "INSERT INTO user_preferences(user_key,pref_key,value_json,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_key,pref_key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at",
                (str(user_key), str(pref_key), json.dumps(value, ensure_ascii=False), time.time()),
            )

    # ---------- update notification state ----------
    def get_update_state(self, key, default=None):
        with self._lock:
            row = self._conn.execute("SELECT value FROM update_state WHERE key=?", (str(key),)).fetchone()
        return default if row is None else row[0]

    def set_update_state(self, key, value):
        with self._lock:
            self._conn.execute(
                "INSERT INTO update_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(key), str(value)),
            )


class PersistentQueue(MutableSequence):
    """List-like SQLite-backed queue with no application-level item ceiling."""

    def __init__(self, store: StateStore):
        self.store = store

    def __len__(self):
        return self.store.queue_count()

    def _normalize_index(self, index, *, allow_end=False):
        size = len(self)
        if index < 0:
            index += size
        max_allowed = size if allow_end else size - 1
        if index < 0 or index > max_allowed:
            raise IndexError("queue index out of range")
        return index

    def _row_at(self, index):
        index = self._normalize_index(index)
        with self.store._lock:
            row = self.store._conn.execute(
                "SELECT seq,payload FROM queue_entries ORDER BY seq LIMIT 1 OFFSET ?", (index,)
            ).fetchone()
        if row is None:
            raise IndexError("queue index out of range")
        return row

    @staticmethod
    def _decode(payload):
        return json.loads(payload)

    @staticmethod
    def _encode(value):
        if not isinstance(value, dict):
            value = dict(value)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if step != 1:
                return [self[i] for i in range(start, stop, step)]
            count = max(0, stop - start)
            if count == 0:
                return []
            with self.store._lock:
                rows = self.store._conn.execute(
                    "SELECT payload FROM queue_entries ORDER BY seq LIMIT ? OFFSET ?", (count, start)
                ).fetchall()
            return [self._decode(row[0]) for row in rows]
        return self._decode(self._row_at(index)["payload"])

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            values = list(value)
            if step != 1:
                indices = list(range(start, stop, step))
                if len(indices) != len(values):
                    raise ValueError("attempt to assign sequence of size mismatch")
                for idx, item in zip(indices, values):
                    self[idx] = item
                return
            # Efficient common case: shuffle replaces a same-length tail.
            with self.store.transaction() as db:
                rows = db.execute(
                    "SELECT seq FROM queue_entries ORDER BY seq LIMIT ? OFFSET ?",
                    (max(0, stop - start), start),
                ).fetchall()
                if len(rows) == len(values):
                    db.executemany(
                        "UPDATE queue_entries SET payload=? WHERE seq=?",
                        [(self._encode(item), int(row["seq"])) for row, item in zip(rows, values)],
                    )
                    return
            # Rare general slice resize: materialize only the operation boundary.
            for idx in range(stop - 1, start - 1, -1):
                del self[idx]
            for offset, item in enumerate(values):
                self.insert(start + offset, item)
            return
        row = self._row_at(index)
        with self.store._lock:
            self.store._conn.execute(
                "UPDATE queue_entries SET payload=? WHERE seq=?", (self._encode(value), int(row["seq"]))
            )

    def __delitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            for idx in reversed(list(range(start, stop, step))):
                del self[idx]
            return
        row = self._row_at(index)
        with self.store._lock:
            self.store._conn.execute("DELETE FROM queue_entries WHERE seq=?", (int(row["seq"]),))

    def _reindex(self, db):
        # Rebuild ordering inside the same transaction instead of borrowing a
        # numeric namespace (negative seq values can legitimately occur after
        # many front insertions). This cannot collide with an existing PK.
        db.execute("CREATE TEMP TABLE IF NOT EXISTS queue_reindex_tmp(payload TEXT NOT NULL)")
        db.execute("DELETE FROM queue_reindex_tmp")
        db.execute("INSERT INTO queue_reindex_tmp(payload) SELECT payload FROM queue_entries ORDER BY seq")
        db.execute("DELETE FROM queue_entries")
        rows = db.execute("SELECT payload FROM queue_reindex_tmp").fetchall()
        db.executemany(
            "INSERT INTO queue_entries(seq,payload) VALUES(?,?)",
            [((i + 1) * _QUEUE_GAP, row[0]) for i, row in enumerate(rows)],
        )
        db.execute("DELETE FROM queue_reindex_tmp")

    def _seq_for_insert(self, db, index):
        size = int(db.execute("SELECT COUNT(*) FROM queue_entries").fetchone()[0])
        if size == 0:
            return _QUEUE_GAP
        if index <= 0:
            first = int(db.execute("SELECT MIN(seq) FROM queue_entries").fetchone()[0])
            return first - _QUEUE_GAP
        if index >= size:
            last = int(db.execute("SELECT MAX(seq) FROM queue_entries").fetchone()[0])
            return last + _QUEUE_GAP
        rows = db.execute(
            "SELECT seq FROM queue_entries ORDER BY seq LIMIT 2 OFFSET ?", (index - 1,)
        ).fetchall()
        left, right = int(rows[0][0]), int(rows[1][0])
        if right - left <= 1:
            self._reindex(db)
            rows = db.execute(
                "SELECT seq FROM queue_entries ORDER BY seq LIMIT 2 OFFSET ?", (index - 1,)
            ).fetchall()
            left, right = int(rows[0][0]), int(rows[1][0])
        return left + (right - left) // 2

    def insert(self, index, value):
        size = len(self)
        if index < 0:
            index = max(0, size + index)
        index = min(max(0, index), size)
        with self.store.transaction() as db:
            seq = self._seq_for_insert(db, index)
            db.execute("INSERT INTO queue_entries(seq,payload) VALUES(?,?)", (seq, self._encode(value)))

    def append(self, value):
        with self.store._lock:
            row = self.store._conn.execute("SELECT MAX(seq) FROM queue_entries").fetchone()
            seq = (int(row[0]) if row and row[0] is not None else 0) + _QUEUE_GAP
            self.store._conn.execute(
                "INSERT INTO queue_entries(seq,payload) VALUES(?,?)", (seq, self._encode(value))
            )

    def extend(self, values):
        # Stream inserts in bounded batches so an arbitrarily large iterable
        # does not need a second full in-memory copy before it reaches SQLite.
        with self.store.transaction() as db:
            row = db.execute("SELECT MAX(seq) FROM queue_entries").fetchone()
            seq = int(row[0]) if row and row[0] is not None else 0
            batch = []
            for value in values:
                seq += _QUEUE_GAP
                batch.append((seq, self._encode(value)))
                if len(batch) >= 1000:
                    db.executemany("INSERT INTO queue_entries(seq,payload) VALUES(?,?)", batch)
                    batch.clear()
            if batch:
                db.executemany("INSERT INTO queue_entries(seq,payload) VALUES(?,?)", batch)

    def shuffle_from(self, start=0):
        """Shuffle the tail using SQLite temp storage, not a Python list.

        There is intentionally no queue-length ceiling. ORDER BY random() is
        O(n), as any true shuffle must touch the tail, but SQLite can spill its
        temporary work to disk instead of forcing all queue payloads into RAM.
        """
        size = len(self)
        start = max(0, min(int(start), size))
        if size - start <= 1:
            return
        with self.store.transaction() as db:
            if start:
                row = db.execute(
                    "SELECT seq FROM queue_entries ORDER BY seq LIMIT 1 OFFSET ?",
                    (start - 1,),
                ).fetchone()
                boundary = int(row[0])
                where_sql = "WHERE seq>?"
                params = (boundary,)
            else:
                boundary = 0
                where_sql = ""
                params = ()
            db.execute(
                "CREATE TEMP TABLE IF NOT EXISTS queue_shuffle_tmp("
                "ord INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT NOT NULL)"
            )
            db.execute("DELETE FROM queue_shuffle_tmp")
            db.execute(
                f"INSERT INTO queue_shuffle_tmp(payload) "
                f"SELECT payload FROM queue_entries {where_sql} ORDER BY random()",
                params,
            )
            if start:
                db.execute("DELETE FROM queue_entries WHERE seq>?", (boundary,))
            else:
                db.execute("DELETE FROM queue_entries")
            db.execute(
                "INSERT INTO queue_entries(seq,payload) "
                "SELECT ? + ord * ?, payload FROM queue_shuffle_tmp ORDER BY ord",
                (boundary, _QUEUE_GAP),
            )
            db.execute("DELETE FROM queue_shuffle_tmp")

    def clear(self):
        with self.store._lock:
            self.store._conn.execute("DELETE FROM queue_entries")

    def __iter__(self) -> Iterator[dict]:
        after = None
        while True:
            items, after = self.store.queue_page(after_seq=after, limit=512)
            if not items:
                return
            for item in items:
                yield item
            if len(items) < 512:
                return

    def replace_all(self, items):
        self.store.replace_queue(items)
