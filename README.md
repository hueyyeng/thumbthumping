# thumbthumping

Fast 3D model thumbnails via [F3D](https://github.com/graphicslab/f3d). Here I stand... at 512x512.

Generates quarter-view perspective thumbnails and optional 6-view orthographic atlases from any 3D file F3D can read (FBX, OBJ, GLB, PLY, STL, etc.). Caches results in a single SQLite database keyed by content fingerprint — no orphaned files, portable everywhere.

## Requirements

- **Python 3.11+** (stdlib only)
- **[F3D](https://github.com/graphicslab/f3d)** on PATH (or set `F3D_EXE` env var)

Optional:
- **ImageMagick** (`magick montage`) for 6-view stitching on Linux
- **Pillow** (`pip install thumbthumping[sixview]`) as cross-platform fallback

## Install

```bash
# Basic (quarter view + stats only, zero deps)
pip install .

# With 6-view support
pip install ".[sixview]"
```

Or run directly:

```bash
python -m thumbthumping generate model.fbx
```

## Usage

```
thumbthumping generate model.fbx          # Generate quarter view thumbnail
thumbthumping generate model.fbx --sixview # Also generate 6-view atlas
thumbthumping list                        # List all cached thumbnails
thumbthumping query model.fbx             # Query cache entry
thumbthumping query model.fbx --base64    # Return blob data as base64
thumbthumping delete model.fbx            # Remove from cache
thumbthumping clear                       # Wipe entire cache
```

All commands accept `-v` for debug logging.

## Cache

Thumbnails are stored as **BLOBs inside a single SQLite database** (`~/.thumbthumping/cache.db`). No separate image files to manage or orphan.

Cache entries are keyed by **content fingerprint** — three byte samples from each file (header, mid-point, tail) hashed with SHA-256. This avoids slow full-file MD5 reads over network storage while still detecting duplicate files across different paths or machines.

Override cache location: `THUMBTHUMPING_CACHE_DIR=/path/to/dir`

## Output

- **Quarter view**: 512x512 perspective render, gray model on dark background
- **Six-view atlas**: 6 orthographic views (front/back/left/right/top/bottom) stitched into a 3×2 grid at 1536x1024

Both stored as PNG BLOBs in SQLite. Use `query --base64` to retrieve base64-encoded data for JSON/web consumption.

## CLI Subcommands

### generate
Generate thumbnail(s) for a 3D file. Checks cache first — skips if content fingerprint matches.

```bash
thumbthumping generate W:/assets/character/model_v2.fbx --sixview
```

### query
Show cached entry metadata and blob size. Use `--base64` to output raw PNG data as base64 strings.

```bash
thumbthumping query model.fbx
# path:      /path/to/model.fbx
# quarter_blob: <52,318 bytes (use --base64 to decode)>
# sixview_blob: <not cached>
# vertices:  15,234
# faces:     12,098
# has_animation: no
```

### list
Show all cached entries with geometry stats.

```bash
thumbthumping list
#   [A] 15,234 verts  character_v2
#   [-] 8,901 verts  prop_table
#
# 2 entries total. DB: /home/user/.thumbthumbing/cache.db
```

### delete / clear
Remove individual entries or wipe the entire cache.

```bash
thumbthumping delete model.fbx    # Remove one entry
thumbthumping clear                # Wipe all
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `F3D_EXE` | Path to F3D binary | Searches PATH for `f3d` |
| `THUMBTHUMPING_CACHE_DIR` | Cache directory | `~/.thumbthumping/` |
