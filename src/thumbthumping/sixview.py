"""Generate a 2x3 orthographic views atlas (front, back, left, right, top, bottom)."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .renderer import find_f3d

log = logging.getLogger(__name__)

# Standard orthographic views (Maya convention: Y=up)
VIEWS = [
    ("front",  "0,0,1",  "0,1,0"),
    ("back",   "0,0,-1", "0,1,0"),
    ("left",   "-1,0,0", "0,1,0"),
    ("right",  "1,0,0",  "0,1,0"),
    ("top",    "0,-1,0", "0,0,-1"),
    ("bottom", "0,1,0",  "0,0,1"),
]

COLS = 3  # 3 columns x 2 rows


def find_magick() -> Optional[str]:
    """Find ImageMagick magick executable on PATH."""
    return shutil.which("magick")


def _render_single_view(
    fbx_path: str,
    output_path: str,
    direction: str,
    view_up: str,
    width: int = 512,
    height: int = 512,
) -> bool:
    """Render one orthographic view using F3D."""
    cmd = [
        find_f3d(),
        "--output", output_path,
        "--resolution", f"{width},{height}",
        "--camera-orthographic=true",
        "--camera-direction", direction,
        "--camera-view-up", view_up,
        "--color", "0.65,0.65,0.65",
        "--background-color", "0.2,0.2,0.2",
        "--grid=false", "--axis=false",
        "--filename=false", "--notifications=false",
        fbx_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode == 0 and Path(output_path).exists()


def generate_sixview(
    fbx_path: str,
    output_path: str,
    width: int = 512,
    height: int = 512,
) -> Optional[str]:
    """Generate a 2x3 orthographic views atlas.

    Args:
        fbx_path: Path to the input 3D file.
        output_path: Output PNG path for the stitched atlas.
        width: Per-view image width.
        height: Per-view image height.

    Returns:
        Output path if successful, None otherwise.
    """
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp_files = []
    view_paths = []

    try:
        for name, direction, view_up in VIEWS:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            tmp_files.append(tmp.name)

            log.info("Rendering %s view...", name)
            if not _render_single_view(fbx_path, tmp.name, direction, view_up, width, height):
                log.error("Failed to render %s view", name)
                return None
            view_paths.append(tmp.name)

        # Stitch using ImageMagick montage (preferred) or Pillow fallback
        if find_magick():
            log.debug("Stitching with ImageMagick...")
            _stitch_with_magick(view_paths, output_path, width, height)
        else:
            try:
                log.debug("ImageMagick not found, stitching with Pillow...")
                _stitch_with_pillow(view_paths, output_path)
            except ImportError:
                log.warning(
                    "Neither ImageMagick nor Pillow available. "
                    "Install Pillow: pip install thumbthumping[sixview]"
                )
                # Fallback: save first view only
                import shutil
                shutil.copy2(view_paths[0], output_path)
                return output_path

        if Path(output_path).exists():
            size = Path(output_path).stat().st_size
            log.info("OK: %s (%d bytes, %dx%d atlas)", output_path, size, width * COLS, height * 2)
            return output_path

        return None

    finally:
        for f in tmp_files:
            if os.path.exists(f):
                os.unlink(f)


def _stitch_with_magick(view_paths: list[str], output_path: str, width: int = 512, height: int = 512) -> None:
    """Stitch individual view images into a grid atlas using ImageMagick montage."""
    subprocess.run(
        [find_magick(), "montage"] +
        ["-tile", f"{COLS}x"] +
        ["-geometry", f"{width}x{height}+0+0"] +
        view_paths +
        [output_path],
        capture_output=True, text=True, timeout=30,
    )


def _stitch_with_pillow(view_paths: list[str], output_path: str) -> None:
    """Stitch individual view images into a grid atlas using Pillow.

    Used as fallback when ImageMagick is not available.
    Requires Pillow: pip install thumbthumping[sixview]
    """
    from PIL import Image

    imgs = [Image.open(p).convert("RGBA") for p in view_paths]
    w, h = imgs[0].size  # all should be same size (512x512)
    rows = (len(imgs) + COLS - 1) // COLS

    atlas = Image.new("RGBA", (w * COLS, h * rows), (0, 0, 0, 0))
    for i, img in enumerate(imgs):
        col = i % COLS
        row = i // COLS
        atlas.paste(img, (col * w, row * h))

    # Save as PNG (strip alpha if single-channel)
    atlas.convert("RGB").save(output_path, "PNG")
