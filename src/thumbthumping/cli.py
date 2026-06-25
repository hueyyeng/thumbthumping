"""CLI entry point for thumbthumping."""
from __future__ import annotations

import argparse
import base64
import logging
import sys
from pathlib import Path

from .cache import (
    db_path,
    delete_from_cache,
    init_db,
    list_all,
    lookup_cache,
    save_to_cache,
)
from .renderer import generate_quarter_view, get_stats
from .sixview import generate_sixview

log = logging.getLogger("thumbthumping")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler()
    handler.setLevel(level)
    fmt = logging.Formatter("%(levelname)-5s %(message)s")
    handler.setFormatter(fmt)
    root = logging.getLogger("thumbthumping")
    root.setLevel(level)
    root.addHandler(handler)


def _cmd_generate(args: argparse.Namespace) -> int:
    fbx_path = str(Path(args.file).resolve())

    # Check cache
    cached = lookup_cache(fbx_path)
    if cached and cached.get("quarter_blob"):
        quarter_size = len(cached["quarter_blob"])
        sixview_size = len(cached["sixview_blob"]) if cached.get("sixview_blob") else 0
        print(f"CACHED: {fbx_path}")
        print(f"  quarter:   {quarter_size:,} bytes")
        if sixview_size > 0:
            print(f"  sixview:   {sixview_size:,} bytes")
        if cached.get("vertices"):
            print(f"  vertices:  {cached['vertices']:,}")
        if cached.get("faces"):
            print(f"  faces:     {cached['faces']:,}")
        return 0

    import tempfile

    # Render to temp files first, then read as blobs
    with tempfile.TemporaryDirectory() as tmpdir:
        quarter_tmp = Path(tmpdir) / "quarter.png"
        sixview_tmp = Path(tmpdir) / "sixview.png"

        # Generate quarter view
        log.info("Generating quarter view...")
        ok = generate_quarter_view(fbx_path, str(quarter_tmp))
        if not ok:
            print(f"Error: Failed to generate quarter view for {args.file}", file=sys.stderr)
            return 1

        quarter_blob = quarter_tmp.read_bytes()

        # Optionally generate sixview
        sixview_blob = None
        if args.sixview:
            log.info("Generating 6-view atlas...")
            ok = generate_sixview(fbx_path, str(sixview_tmp))
            if ok:
                sixview_blob = sixview_tmp.read_bytes()
            else:
                log.warning("Failed to generate sixview atlas")

    # Extract stats
    log.info("Extracting stats...")
    stats = get_stats(fbx_path)

    # Save to cache (blobs)
    save_to_cache(
        filepath=fbx_path,
        quarter_blob=quarter_blob,
        sixview_blob=sixview_blob,
        vertices=stats.get("vertices"),
        faces=stats.get("faces"),
        has_animation=stats.get("has_animation"),
    )

    print(f"Generated: {fbx_path}")
    print(f"  quarter:   {len(quarter_blob):,} bytes")
    if sixview_blob:
        print(f"  sixview:   {len(sixview_blob):,} bytes")
    if stats.get("vertices"):
        print(f"  vertices:  {stats['vertices']:,}")
    if stats.get("faces"):
        print(f"  faces:     {stats['faces']:,}")
    print(f"  cached in: {db_path()}")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    filepath = str(Path(args.file).resolve())
    cached = lookup_cache(filepath)

    if not cached:
        # Check if we have an entry but file changed
        from .cache import _connect
        conn = _connect()
        row = conn.execute("SELECT path, generated_at FROM thumbs WHERE path = ?", (filepath,)).fetchone()
        conn.close()
        if row:
            print("Cache miss -- file modified since last generation.")
            print(f"  path:      {row['path']}")
            print(f"  generated: {row['generated_at']}")
        else:
            print(f"Not in cache: {args.file}")
        return 0

    result = {}
    for key, val in cached.items():
        if isinstance(val, bytes):
            if args.base64:
                result[key] = base64.b64encode(val).decode("ascii")
            else:
                result[key] = f"<{len(val):,} bytes (use --base64 to decode)>"
        elif val is True:
            result[key] = "yes"
        elif val is False:
            result[key] = "no"
        else:
            result[key] = val

    print(f"Cached: {Path(args.file).name}")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    entries = list_all()
    if not entries:
        print("Cache is empty.")
        return 0

    for e in entries:
        stem = Path(e["path"]).stem
        v = f"{e['vertices']:,}" if e.get("vertices") else "?"
        anim = "A" if e.get("has_animation") else "-"
        print(f"  [{anim}] {v} verts  {stem}")
    print(f"\n{len(entries)} entries total. DB: {db_path()}")
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    filepath = str(Path(args.file).resolve())
    if delete_from_cache(filepath):
        print(f"Deleted from cache: {args.file}")
    else:
        print(f"Not in cache: {args.file}")
    return 0


def _cmd_clear(args: argparse.Namespace) -> int:
    from .cache import clear_cache
    n = clear_cache()
    print(f"Cleared {n} entries from cache.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="thumbthumping",
        description="Fast 3D model thumbnails via F3D. Here I stand... at 512x512.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")

    subs = parser.add_subparsers(dest="command", required=True)

    # generate
    p_gen = subs.add_parser("generate", help="Generate thumbnail(s) for a 3D file")
    p_gen.add_argument("file", help="Path to FBX/OBJ/GLB/PLY file")
    p_gen.add_argument("--sixview", action="store_true", help="Also generate 6-view atlas")

    # list
    subs.add_parser("list", help="List all cached thumbnails")

    # query
    p_q = subs.add_parser("query", help="Query cache for a specific file")
    p_q.add_argument("file", help="Path to check")
    p_q.add_argument("--base64", action="store_true", help="Return blob data as base64")

    # delete
    p_del = subs.add_parser("delete", help="Remove entry from cache")
    p_del.add_argument("file", help="Path to remove")

    # clear
    subs.add_parser("clear", help="Wipe entire cache")

    args = parser.parse_args()
    _setup_logging(args.verbose)
    init_db()

    dispatch = {
        "generate": _cmd_generate,
        "list": _cmd_list,
        "query": _cmd_query,
        "delete": _cmd_delete,
        "clear": _cmd_clear,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
