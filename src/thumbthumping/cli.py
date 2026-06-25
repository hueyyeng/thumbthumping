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
    list_all_with_blobs,
    lookup_cache,
    save_to_cache,
    set_cache_dir,
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


def _parse_resolution(val: str) -> tuple[int, int]:
    """Parse 'WxH' resolution string."""
    try:
        w, h = val.split("x")
        return int(w), int(h)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(
            f"Invalid resolution '{val}'. Use format like 512x512 or 1024x1024."
        )


def _cmd_generate(args: argparse.Namespace) -> int:
    fbx_path = str(Path(args.file).resolve())
    width, height = args.resolution

    # Check cache
    cached = lookup_cache(fbx_path, width, height)
    if cached and cached.get("quarter_blob"):
        quarter_size = len(cached["quarter_blob"])
        sixview_size = len(cached["sixview_blob"]) if cached.get("sixview_blob") else 0
        print(f"CACHED: {fbx_path}")
        print(f"  resolution: {cached['resolution']}")
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
        ok = generate_quarter_view(fbx_path, str(quarter_tmp), width, height)
        if not ok:
            print(f"Error: Failed to generate quarter view for {args.file}", file=sys.stderr)
            return 1

        quarter_blob = quarter_tmp.read_bytes()

        # Optionally generate sixview
        sixview_blob = None
        if args.sixview:
            log.info("Generating 6-view atlas...")
            ok = generate_sixview(fbx_path, str(sixview_tmp), width, height)
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
        width=width,
        height=height,
    )

    print(f"Generated: {fbx_path}")
    print(f"  resolution: {width}x{height}")
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
    width, height = args.resolution
    cached = lookup_cache(args.file, width, height)

    if not cached:
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
        h = e.get("content_hash", "?")[:8]
        res = e.get("resolution", "?")
        v = f"{e['vertices']:,}" if e.get("vertices") else "?"
        anim = "A" if e.get("has_animation") else "-"
        print(f"  [{anim}] {v} verts  {stem}  ({h})  {res}")
    print(f"\n{len(entries)} entries total. DB: {db_path()}")
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    width, height = args.resolution
    if delete_from_cache(args.file, width, height):
        print(f"Deleted from cache: {args.file}")
    else:
        print(f"Not in cache: {args.file}")
    return 0


def _cmd_clear(args: argparse.Namespace) -> int:
    from .cache import clear_cache
    n = clear_cache()
    print(f"Cleared {n} entries from cache.")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = list_all_with_blobs()
    if not entries:
        print("Cache is empty — nothing to export.")
        return 0

    quarter_dir = out_dir / "quarter"
    sixview_dir = out_dir / "sixview"
    quarter_dir.mkdir(parents=True, exist_ok=True)
    if args.sixview:
        sixview_dir.mkdir(parents=True, exist_ok=True)

    exported_q = 0
    exported_s = 0
    for entry in entries:
        stem = Path(entry["path"]).stem
        h = entry.get("content_hash", "")[:8]
        res = entry.get("resolution", "512x512")

        if entry.get("quarter_blob"):
            dest = quarter_dir / f"{stem}_{h}_{res}.png"
            dest.write_bytes(entry["quarter_blob"])
            exported_q += 1

        if args.sixview and entry.get("sixview_blob"):
            dest = sixview_dir / f"{stem}_{h}_{res}.png"
            dest.write_bytes(entry["sixview_blob"])
            exported_s += 1

    print(f"Exported {exported_q} quarter-view PNG(s) to {quarter_dir}")
    if args.sixview:
        print(f"Exported {exported_s} sixview PNG(s) to {sixview_dir}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="thumbthumping",
        description="Fast 3D model thumbnails via F3D. Here I stand... at 512x512.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    parser.add_argument(
        "-C", "--cache-dir",
        default=None,
        metavar="PATH",
        help="Path for the cache directory (default: ~/.thumbthumping)",
    )

    subs = parser.add_subparsers(dest="command", required=True)

    # generate
    p_gen = subs.add_parser("generate", help="Generate thumbnail(s) for a 3D file")
    p_gen.add_argument("file", help="Path to FBX/OBJ/GLB/PLY file")
    p_gen.add_argument("--sixview", action="store_true", help="Also generate 6-view atlas")
    p_gen.add_argument(
        "-R", "--resolution",
        default="512x512",
        type=_parse_resolution,
        metavar="WxH",
        help="Output resolution (default: 512x512)",
    )

    # list
    subs.add_parser("list", help="List all cached thumbnails")

    # query
    p_q = subs.add_parser("query", help="Query cache for a specific file")
    p_q.add_argument("file", help="Path to check")
    p_q.add_argument("--base64", action="store_true", help="Return blob data as base64")
    p_q.add_argument(
        "-R", "--resolution",
        default="512x512",
        type=_parse_resolution,
        metavar="WxH",
        help="Resolution to look up (default: 512x512)",
    )

    # delete
    p_del = subs.add_parser("delete", help="Remove entry from cache")
    p_del.add_argument("file", help="Path to remove")
    p_del.add_argument(
        "-R", "--resolution",
        default="512x512",
        type=_parse_resolution,
        metavar="WxH",
        help="Resolution to delete (default: 512x512)",
    )

    # clear
    subs.add_parser("clear", help="Wipe entire cache")

    # export
    p_exp = subs.add_parser("export", help="Export all cached thumbnails to disk")
    p_exp.add_argument(
        "output",
        help="Output directory (created if it doesn't exist)",
    )
    p_exp.add_argument(
        "--sixview", action="store_true",
        help="Also export sixview atlases (exports quarter views by default)",
    )

    args = parser.parse_args()
    _setup_logging(args.verbose)
    if args.cache_dir:
        set_cache_dir(args.cache_dir)
    init_db()

    dispatch = {
        "generate": _cmd_generate,
        "list": _cmd_list,
        "query": _cmd_query,
        "delete": _cmd_delete,
        "clear": _cmd_clear,
        "export": _cmd_export,
    }
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
