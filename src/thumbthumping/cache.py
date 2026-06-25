"""SQLite cache layer — stores thumbnails as BLOBs, keyed by path + mtime."""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".thumbthumping"


def _cache_dir() -> Path:
    env = os.environ.get("THUMBTHUMPING_CACHE_DIR")
    if env:
        return Path(env)
    return _DEFAULT_CACHE_DIR


def _db_path() -> Path:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "cache.db"


# Schema version — bump when changing table structure
_SCHEMA_V = 1

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS thumbs (
    path          TEXT PRIMARY KEY,
    mtime         REAL NOT NULL,
    size          INTEGER NOT NULL,
    quarter_blob  BLOB,
    sixview_blob  BLOB,
    vertices      INTEGER,
    faces         INTEGER,
    has_animation BOOLEAN,
    generated_at  TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_v', '{_SCHEMA_V}');
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA_SQL)
    return conn


def init_db() -> None:
    """Initialize the cache database (creates tables if needed).

    Safe to call multiple times. Usually called at CLI startup.
    """
    with _connect():
        pass  # schema creation happens in _connect()
    log.debug("Cache DB ready: %s", _db_path())


def lookup_cache(filepath: str) -> dict | None:
    """Look up a cached entry by filepath.

    Returns dict if path matches AND mtime/size unchanged, else None.
    Blob columns (quarter_blob, sixview_blob) are included in the result.
    """
    p = Path(filepath).resolve()
    info = p.stat()

    conn = _connect()
    row = conn.execute("SELECT * FROM thumbs WHERE path = ?", (str(p),)).fetchone()
    conn.close()

    if row and row["mtime"] == info.st_mtime and row["size"] == info.st_size:
        return dict(row)
    return None


def save_to_cache(
    filepath: str,
    quarter_blob: bytes | None = None,
    sixview_blob: bytes | None = None,
    vertices: int | None = None,
    faces: int | None = None,
    has_animation: bool | None = None,
) -> dict:
    """Save or update a cache entry with raw PNG bytes.

    Returns the saved row as dict.
    """
    p = Path(filepath).resolve()
    info = p.stat()

    conn = _connect()
    conn.execute(
        """INSERT OR REPLACE INTO thumbs
           (path, mtime, size, quarter_blob, sixview_blob, vertices, faces, has_animation)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            str(p),
            info.st_mtime,
            info.st_size,
            quarter_blob,
            sixview_blob,
            vertices,
            faces,
            has_animation,
        ),
    )
    conn.commit()

    row = conn.execute("SELECT * FROM thumbs WHERE path = ?", (str(p),)).fetchone()
    conn.close()
    return dict(row) if row else {}


def delete_from_cache(filepath: str) -> bool:
    """Delete a cache entry.

    Returns True if entry was found and deleted.
    """
    p = Path(filepath).resolve()
    conn = _connect()
    cursor = conn.execute("DELETE FROM thumbs WHERE path = ?", (str(p),))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def list_all() -> list[dict]:
    """Return all cached entries (metadata only, no blobs).

    Blob columns are excluded to keep the result lightweight.
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT path, mtime, size, vertices, faces, has_animation, generated_at "
        "FROM thumbs ORDER BY generated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_cache() -> int:
    """Wipe the entire cache.

    Returns number of entries cleared.
    """
    conn = _connect()
    count = conn.execute("SELECT COUNT(*) FROM thumbs").fetchone()[0]
    conn.execute("DELETE FROM thumbs")
    conn.commit()
    conn.close()
    return count


def db_path() -> Path:
    """Return the current database path."""
    return _db_path()
