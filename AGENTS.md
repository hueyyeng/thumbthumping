# AGENTS.md — thumbthumping

## Pure Python Only

This project uses **stdlib exclusively**. No pip packages required for core usage. The only external dependencies are CLI binaries:

- **F3D** (`f3d`) — Required render engine. Found via PATH or `F3D_EXE` env var.
- **ImageMagick** (`magick montage`) — Optional atlas stitcher (Linux). Falls back to Pillow if unavailable.

**Do not introduce new pip packages.** If you think one is needed, ask the user first and explain why stdlib can't solve it.

## F3D / Magick Discovery

Before any render code runs:

1. `shutil.which("f3d")` → if missing, check `F3D_EXE` env var
2. `shutil.which("magick")` → optional, fallback to Pillow

**If F3D cannot be found:** Stop and ask the user where it's installed. Do not proceed with guessed paths or stub implementations that will fail when the user returns later.

## Ruff Mandatory

All code edits must pass `ruff check` before declaring work done:

```bash
ruff check src/thumbthumping/
```

**If ruff is not available:** Ask the user either (a) if it's okay to install ruff, or (b) point you to a working ruff binary path. **Do not proceed with code changes without linting capability.** This prevents the user from inheriting broken state when they develop with an AI agent later.
