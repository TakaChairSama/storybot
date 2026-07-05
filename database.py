"""SQLite database layer for StoryBot."""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.environ.get("STORYBOT_DB", "storybot.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS worlds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
                source_url TEXT NOT NULL,
                source_type TEXT NOT NULL,
                title TEXT DEFAULT '',
                raw_content TEXT DEFAULT '',
                ai_analysis TEXT DEFAULT '{}',
                txt_path TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                world_id INTEGER NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                story_ids TEXT DEFAULT '[]',
                UNIQUE(world_id, name)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
        """)
        conn.commit()


# ── World helpers ──────────────────────────────────────────────────────────────

def get_worlds():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM worlds ORDER BY name").fetchall()
        return [dict(r) for r in rows]


def create_world(name, description=""):
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO worlds (name, description) VALUES (?, ?)", (name, description)
        )
        conn.commit()
        return cur.lastrowid


def delete_world(world_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM worlds WHERE id = ?", (world_id,))
        conn.commit()


def update_world(world_id, name=None, description=None):
    with get_connection() as conn:
        if name is not None:
            conn.execute("UPDATE worlds SET name = ? WHERE id = ?", (name, world_id))
        if description is not None:
            conn.execute("UPDATE worlds SET description = ? WHERE id = ?", (description, world_id))
        conn.commit()


# ── Story helpers ──────────────────────────────────────────────────────────────

def get_stories(world_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM stories WHERE world_id = ? ORDER BY created_at DESC", (world_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["ai_analysis"] = json.loads(d["ai_analysis"] or "{}")
            result.append(d)
        return result


def get_story(story_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["ai_analysis"] = json.loads(d["ai_analysis"] or "{}")
        return d


def create_story(world_id, source_url, source_type, title="", raw_content="",
                 ai_analysis=None, txt_path=""):
    ai_json = json.dumps(ai_analysis or {})
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO stories
               (world_id, source_url, source_type, title, raw_content, ai_analysis, txt_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (world_id, source_url, source_type, title, raw_content, ai_json, txt_path),
        )
        conn.commit()
        return cur.lastrowid


def update_story(story_id, **kwargs):
    if "ai_analysis" in kwargs and isinstance(kwargs["ai_analysis"], dict):
        kwargs["ai_analysis"] = json.dumps(kwargs["ai_analysis"])
    kwargs["updated_at"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [story_id]
    with get_connection() as conn:
        conn.execute(f"UPDATE stories SET {cols} WHERE id = ?", vals)
        conn.commit()


def delete_story(story_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
        conn.commit()


# ── Character helpers ──────────────────────────────────────────────────────────

def get_characters(world_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM characters WHERE world_id = ? ORDER BY name", (world_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["story_ids"] = json.loads(d["story_ids"] or "[]")
            result.append(d)
        return result


def upsert_character(world_id, name, description="", story_id=None):
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM characters WHERE world_id = ? AND name = ?", (world_id, name)
        ).fetchone()
        if existing:
            story_ids = json.loads(existing["story_ids"] or "[]")
            if story_id and story_id not in story_ids:
                story_ids.append(story_id)
            new_desc = description if description else existing["description"]
            conn.execute(
                "UPDATE characters SET description = ?, story_ids = ? WHERE id = ?",
                (new_desc, json.dumps(story_ids), existing["id"]),
            )
        else:
            ids = json.dumps([story_id] if story_id else [])
            conn.execute(
                "INSERT INTO characters (world_id, name, description, story_ids) VALUES (?,?,?,?)",
                (world_id, name, description, ids),
            )
        conn.commit()


# ── Settings helpers ───────────────────────────────────────────────────────────

def get_setting(key, default=""):
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def get_all_settings():
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
