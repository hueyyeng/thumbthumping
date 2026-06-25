"""Render thumbnails using F3D CLI headless."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger(__name__)

# Default appearance (gray model on dark background)
DEFAULT_COLOR = "0.65,0.65,0.65"
DEFAULT_BACKGROUND = "0.2,0.2,0.2"

# Quarter view camera direction (nice 3/4 upright perspective)
QUARTER_DIRECTION = "1,-0.3,1"


def find_f3d() -> str:
    """Find F3D executable on PATH or via env var."""
    # Check env var first
    env_path = os.environ.get("F3D_EXE")
    if env_path and os.path.isfile(env_path):
        return env_path

    # Try PATH
    found = shutil.which("f3d")
    if found:
        return found

    raise FileNotFoundError(
        "F3D not found. Install it or set F3D_EXE env var."
    )


def _build_f3d_cmd(
    fbx_path: str,
    output_path: str,
    camera_flags: list[str],
    width: int = 512,
    height: int = 512,
) -> list[str]:
    """Build F3D command line for rendering."""
    return [
        find_f3d(),
        "--output", output_path,
        "--resolution", f"{width},{height}",
        "--color", DEFAULT_COLOR,
        "--background-color", DEFAULT_BACKGROUND,
        "--grid=false",
        "--axis=false",
        "--filename=false",
        "--notifications=false",
    ] + camera_flags + [fbx_path]


def generate_quarter_view(
    fbx_path: str,
    output_path: str,
    width: int = 512,
    height: int = 512,
) -> Optional[str]:
    """Generate the default quarter (3/4 perspective) view thumbnail.

    Args:
        fbx_path: Path to the input 3D file.
        output_path: Output PNG path.
        width: Output image width.
        height: Output image height.

    Returns:
        Output path if successful, None otherwise.
    """
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = _build_f3d_cmd(
        fbx_path=fbx_path,
        output_path=output_path,
        camera_flags=[
            "--camera-direction", QUARTER_DIRECTION,
            "--camera-view-up", "0,1,0",
        ],
        width=width,
        height=height,
    )

    log.info("Rendering quarter view: %s", Path(fbx_path).name)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode == 0 and Path(output_path).exists():
        size = Path(output_path).stat().st_size
        log.info("OK: %s (%d bytes)", output_path, size)
        return output_path

    log.error("FAIL: quarter view (rc=%d)", result.returncode)
    if result.stderr:
        log.debug("stderr: %s", result.stderr[-500:])
    return None


def get_stats(fbx_path: str) -> Dict[str, object]:
    """Extract geometry stats from a 3D file using F3D headless.

    Returns dict with keys: vertices, faces, has_animation.
    """
    result = subprocess.run(
        [find_f3d(), "--output", "NUL", "--verbose=debug", fbx_path],
        capture_output=True,
        text=True,
        timeout=60,
    )

    output = result.stderr + result.stdout

    # Sum all actors' points and cells (files can have many meshes)
    verts_matches = re.findall(r"Number of points: (\d+)", output)
    faces_matches = re.findall(r"Number of cells: (\d+)", output)

    total_verts = sum(int(v) for v in verts_matches) if verts_matches else None
    total_faces = sum(int(f) for f in faces_matches) if faces_matches else None
    has_anim = "No animation available" not in output if output else None

    return {
        "vertices": total_verts,
        "faces": total_faces,
        "has_animation": has_anim,
    }
