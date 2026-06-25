"""SQLite cache layer — stores thumbnails as BLOBs, keyed by content hash + resolution."""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = Path.home() / ".thumbthumping"
_override_cache_dir: Path | None = None


def set_cache_dir(path: str | Path) -> None:
    """Override the cache directory programmatically.

    Takes precedence over both the env var and the default.
    Must be called before any cache operations (init_db, lookup, etc.).
    """
    global _override_cache_dir
    _override_cache_dir = Path(path)


def _cache_dir() -> Path:
    if _override_cache_dir is not None:
        return _override_cache_dir
    env = os.environ.get("THUMBTHUMPING_CACHE_DIR")
    if env:
        return Path(env)
    return _DEFAULT_CACHE_DIR


def _db_path() -> Path:
    d = _cache_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / "cache.db"


# Schema version — bump when changing table structure
_SCHEMA_V = 3

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS thumbs (
    cache_key     TEXT PRIMARY KEY,
    content_hash  TEXT NOT NULL,
    resolution    TEXT NOT NULL,
    path          TEXT NOT NULL,
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


def _file_hash(filepath: Path) -> str:
    """Compute MD5 hash of the first 1MB of a file.

    Fast enough for network storage (SAMBA) while still being unique
    for deduplication across different paths.
    """
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        h.update(f.read(1 << 20))  # first 1MB
    return h.hexdigest()


def _cache_key(content_hash: str, width: int, height: int) -> str:
    """Build a composite cache key from content hash and resolution."""
    return f"{content_hash}_{width}x{height}"


def _needs_migration(conn: sqlite3.Connection) -> bool:
    """Check if the database schema needs upgrading."""
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_v'").fetchone()
    if row is None:
        return True
    return int(row["value"]) < _SCHEMA_V


def _migrate(conn: sqlite3.Connection) -> None:
    """Drop old schema and recreate with current version."""
    log.warning("Schema migration required — cache will be cleared")
    conn.execute("DROP TABLE IF EXISTS thumbs")
    conn.execute("DROP TABLE IF EXISTS meta")
    conn.executescript(_SCHEMA_SQL)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    if _needs_migration(conn):
        _migrate(conn)
    else:
        # Schema exists but tables may not be fully created (fresh DB edge case)
        conn.executescript(_SCHEMA_SQL)
    return conn


def init_db() -> None:
    """Initialize the cache database (creates tables if needed).

    Safe to call multiple times. Usually called at CLI startup.
    """
    with _connect():
        pass  # schema creation happens in _connect()
    log.debug("Cache DB ready: %s", _db_path())


def lookup_cache(filepath: str, width: int = 512, height: int = 512) -> dict | None:
    """Look up a cached entry by file content hash and resolution.

    Returns dict if the same file content at the requested resolution is cached, else None.
    Blob columns (quarter_blob, sixview_blob) are included in the result.
    """
    p = Path(filepath).resolve()
    fh = _file_hash(p)
    key = _cache_key(fh, width, height)

    conn = _connect()
    row = conn.execute("SELECT * FROM thumbs WHERE cache_key = ?", (key,)).fetchone()
    conn.close()

    return dict(row) if row else None


def save_to_cache(
    filepath: str,
    quarter_blob: bytes | None = None,
    sixview_blob: bytes | None = None,
    vertices: int | None = None,
    faces: int | None = None,
    has_animation: bool | None = None,
    width: int = 512,
    height: int = 512,
) -> dict:
    """Save or update a cache entry with raw PNG bytes.

    Keyed by content hash + resolution — same file at different resolutions
    are stored as separate entries.
    Returns the saved row as dict.
    """
    p = Path(filepath).resolve()
    fh = _file_hash(p)
    key = _cache_key(fh, width, height)
    size = p.stat().st_size

    conn = _connect()
    conn.execute(
        """INSERT OR REPLACE INTO thumbs
           (cache_key, content_hash, resolution, path, size,
            quarter_blob, sixview_blob, vertices, faces, has_animation)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            key,
            fh,
            f"{width}x{height}",
            str(p),
            size,
            quarter_blob,
            sixview_blob,
            vertices,
            faces,
            has_animation,
        ),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM thumbs WHERE cache_key = ?", (key,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def delete_from_cache(filepath: str, width: int = 512, height: int = 512) -> bool:
    """Delete a cache entry by file content hash and resolution.

    Returns True if entry was found and deleted.
    """
    p = Path(filepath).resolve()
    fh = _file_hash(p)
    key = _cache_key(fh, width, height)
    conn = _connect()
    cursor = conn.execute("DELETE FROM thumbs WHERE cache_key = ?", (key,))
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
        "SELECT cache_key, content_hash, resolution, path, size, "
        "vertices, faces, has_animation, generated_at "
        "FROM thumbs ORDER BY generated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_all_with_blobs() -> list[dict]:
    """Return all cached entries including blob data.

    Use for exporting thumbnails to disk.
    """
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM thumbs ORDER BY generated_at DESC"
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
