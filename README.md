# thumbthumping

Fast 3D model thumbnails via [F3D](https://github.com/graphicslab/f3d). Here I stand... at 512x512 (or whatever you want).

Generates quarter-view perspective thumbnails and optional 6-view orthographic atlases from any 3D file F3D can read (FBX, OBJ, GLB, PLY, STL, etc.). Caches results in a single SQLite database keyed by content hash — no orphaned files, portable everywhere.

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
thumbthumping generate model.fbx                    # Generate quarter view thumbnail
thumbthumping generate model.fbx --sixview          # Also generate 6-view atlas
thumbthumping generate model.fbx -R 1024x1024       # Custom resolution
thumbthumping list                                  # List all cached thumbnails
thumbthumping query model.fbx                       # Query cache entry
thumbthumping query model.fbx --base64              # Return blob data as base64
thumbthumping delete model.fbx                      # Remove from cache
thumbthumping clear                                 # Wipe entire cache
thumbthumping export /path/to/output                # Export all PNGs to disk
```

All commands accept `-v` for debug logging and `-C PATH` to set a custom cache directory.

## Cache

Thumbnails are stored as **BLOBs inside a single SQLite database** (`~/.thumbthumping/cache.db`). No separate image files to manage or orphan.

Cache entries are keyed by **first-1MB MD5 hash + resolution** — fast over network storage (SAMBA) while still unique for deduplication. The same file at different resolutions (512, 1024, 2048) are stored as separate entries. Identical files across different paths share a single cache entry per resolution.

Override cache location:
- CLI flag: `-C /path/to/cache` or `--cache-dir /path/to/cache`
- Env var: `THUMBTHUMPING_CACHE_DIR=/path/to/dir`

## Output

- **Quarter view**: Perspective render, gray model on dark background (default 512x512)
- **Six-view atlas**: 6 orthographic views (front/back/left/right/top/bottom) stitched into a 3×2 grid

Both stored as PNG BLOBs in SQLite. Use `query --base64` to retrieve base64-encoded data for JSON/web consumption, or `export` to dump all thumbnails to disk.

## CLI Subcommands

### generate
Generate thumbnail(s) for a 3D file. Checks cache first — skips if content hash and resolution match.

```bash
thumbthumping generate W:/assets/character/model_v2.fbx --sixview
thumbthumping generate model.fbx -R 1024x1024        # Custom resolution
thumbthumping generate model.fbx -C /data/cache      # Custom cache dir
```

### query
Show cached entry metadata and blob size. Use `--base64` to output raw PNG data as base64 strings.

```bash
thumbthumping query model.fbx
# Cached: model.fbx
#   content_hash: a3f1b2c4...
#   resolution: 512x512
#   quarter_blob: <52,318 bytes (use --base64 to decode)>
#   sixview_blob: <not cached>
#   vertices:  15,234
#   faces:     12,098
#   has_animation: no
```

### list
Show all cached entries with geometry stats and content hash.

```bash
thumbthumping list
#   [A] 15,234 verts  character_v2  (a3f1b2c4)  512x512
#   [-] 8,901 verts   prop_table    (7e9d0f1a)  512x512
#
# 2 entries total. DB: /home/user/.thumbthumping/cache.db
```

### delete / clear
Remove individual entries or wipe the entire cache.

```bash
thumbthumping delete model.fbx    # Remove one entry
thumbthumping clear                # Wipe all
```

### export
Export all cached thumbnails as PNG files to a directory. Filenames include the model stem, content hash prefix, and resolution for uniqueness.

```bash
thumbthumping export /output/thumbnails              # Export quarter views
thumbthumping export /output/thumbnails --sixview    # Also export sixview atlases
```

Output structure:
```
/output/thumbnails/
├── quarter/
│   ├── character_v2_a3f1b2c4_512x512.png
│   └── prop_table_7e9d0f1a_512x512.png
└── sixview/
    ├── character_v2_a3f1b2c4_512x512.png
    └── prop_table_7e9d0f1a_512x512.png
```

## Studio Workflow — Automated Thumbnail Pipeline

A common studio setup: scan all FBX assets nightly, generate thumbnails, and export them for a web dashboard or PDF report.

### 1. Scan and generate

```bash
#!/bin/bash
# scripts/update_thumbnails.sh
CACHE_DIR="/mnt/shared/thumbthumping-cache"
OUTPUT_DIR="/var/www/html/asset-browser/thumbnails"
RESOLUTION="1024x1024"

# Find all FBX files across project directories
find /mnt/projects/characters \
     /mnt/projects/props \
     /mnt/projects/environments \
  -name "*.fbx" | while read -r fbx; do
    thumbthumping -C "$CACHE_DIR" generate "$fbx" --sixview -R "$RESOLUTION"
done

# Export all thumbnails to a web-accessible directory
thumbthumping -C "$CACHE_DIR" export "$OUTPUT_DIR" --sixview
```

### 2. Automate with cron

```cron
# Run every night at 2 AM, skip if already running
0 2 * * * flock /tmp/thumbthumping.lock /path/to/scripts/update_thumbnails.sh >> /var/log/thumbthumping.log 2>&1
```

The cache handles deduplication automatically — files that haven't changed are skipped instantly. New or modified FBX files get rendered. Over SAMBA, the first-1MB hash check is fast enough to scan hundreds of files in seconds.

### 3. Serve from anywhere

The exported PNGs are plain files — serve them with Nginx, drop them into a Nuxt dashboard, embed them in a PDF report, or mount the directory on any browser-accessible path. The SQLite DB is portable too — copy it to another machine and point `-C` at its parent directory.

Output structure:
```
/var/www/html/asset-browser/thumbnails/
├── quarter/
│   ├── hero_rig_a3f1b2c4_1024x1024.png
│   ├── prop_chair_7e9d0f1a_1024x1024.png
│   └── env_forest_2b8c3d4e_1024x1024.png
└── sixview/
    ├── hero_rig_a3f1b2c4_1024x1024.png
    ├── prop_chair_7e9d0f1a_1024x1024.png
    └── env_forest_2b8c3d4e_1024x1024.png
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `F3D_EXE` | Path to F3D binary | Searches PATH for `f3d` |
| `THUMBTHUMPING_CACHE_DIR` | Cache directory | `~/.thumbthumping/` |
