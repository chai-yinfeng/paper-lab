"""SQLite is the source of truth; PDF bytes live in the workspace's pdfs/ directory."""

from __future__ import annotations
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def uid():
    return uuid.uuid4().hex


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
 filename TEXT NOT NULL, source TEXT NOT NULL, page_count INTEGER NOT NULL,
 current_page INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_tags (
 paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE, tag TEXT NOT NULL,
 PRIMARY KEY(paper_id,tag));
CREATE TABLE IF NOT EXISTS pages (
 paper_id TEXT NOT NULL REFERENCES papers(id), number INTEGER NOT NULL,
 width REAL NOT NULL, height REAL NOT NULL, text TEXT NOT NULL, words TEXT NOT NULL,
 PRIMARY KEY(paper_id,number));
CREATE TABLE IF NOT EXISTS threads (
 id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id), title TEXT NOT NULL,
 context_mode TEXT NOT NULL DEFAULT 'focused', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS threads_paper ON threads(paper_id, updated_at);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES threads(id), role TEXT NOT NULL,
 content TEXT NOT NULL, anchor TEXT, context TEXT, status TEXT NOT NULL,
 model TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread_id, created_at);
CREATE TABLE IF NOT EXISTS notes (
 id TEXT PRIMARY KEY, paper_id TEXT NOT NULL REFERENCES papers(id), message_id TEXT REFERENCES messages(id),
 content TEXT NOT NULL, anchor TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS notes_paper ON notes(paper_id, updated_at);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, thread_id TEXT NOT NULL REFERENCES threads(id), message_id TEXT NOT NULL REFERENCES messages(id),
 workflow TEXT NOT NULL, status TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
 usage TEXT, trace TEXT, error TEXT, created_at TEXT NOT NULL, finished_at TEXT);
CREATE INDEX IF NOT EXISTS runs_thread ON runs(thread_id, created_at);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

SCHEMA_VERSION = 4


class Store:
    def __init__(self, path: str | Path):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            self.conn.close()
            raise ValueError("工作目录来自更新版本，请升级 Paper Lab。")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        if version == 1:
            self.conn.execute("ALTER TABLE runs ADD COLUMN trace TEXT")
        thread_columns = {
            row[1] for row in self.conn.execute("PRAGMA table_info(threads)").fetchall()
        }
        if "context_mode" not in thread_columns:
            self.conn.execute(
                "ALTER TABLE threads ADD COLUMN context_mode TEXT NOT NULL DEFAULT 'focused'"
            )
        self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        # A process crash must never leave a conversation apparently generating forever.
        with self.conn:
            self.conn.execute(
                "UPDATE messages SET status='interrupted' WHERE status='streaming'"
            )
            self.conn.execute(
                "UPDATE runs SET status='interrupted',finished_at=? WHERE status='running'",
                (stamp(),),
            )

    def all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        if not rows:
            raise LookupError("记录不存在。")
        return rows[0]

    def execute(self, sql, args=()):
        with self.lock, self.conn:
            self.conn.execute(sql, args)

    def setting(self, key, default):
        rows = self.all("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set_setting(self, key, value):
        self.execute(
            "INSERT OR REPLACE INTO settings VALUES (?,?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )

    def close(self):
        self.conn.close()


def decoded(row):
    result = dict(row)
    for key in ("anchor", "context", "usage", "trace", "source", "words"):
        if key in result and result[key] is not None:
            result[key] = json.loads(result[key])
    return result
