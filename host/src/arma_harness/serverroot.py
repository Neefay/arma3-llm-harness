"""The isolated dedicated-server root.

The server reads missions from ``<exe dir>\\MPMissions``. To avoid touching the user's install, the
harness keeps its own root: a copy of ``arma3server_x64.exe`` plus the Steam DLLs, and directory
junctions (read-only use) to the install's data folders. Verified on Arma 3 2.22.

Never delete this folder recursively with a tool that follows junctions; use ``remove()``.
"""
from __future__ import annotations

import filecmp
import shutil
import subprocess
from pathlib import Path

COPIED_FILES = [
    "arma3server_x64.exe",
    "steam_api64.dll",
    "steamclient64.dll",
    "tier0_s64.dll",
    "vstdlib_s64.dll",
    "steam_appid.txt",
]
NOT_LINKED = {"mpmissions", "missions", "launcher", "!workshop", "battleye"}


def _is_junction(p: Path) -> bool:
    try:
        return p.is_junction()
    except OSError:
        return False


def ensure(arma_dir: Path, root: Path) -> dict:
    """Create or repair the server root. Idempotent; refreshes copied files after game updates."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "MPMissions").mkdir(exist_ok=True)
    copied, linked = [], []
    for name in COPIED_FILES:
        src, dst = arma_dir / name, root / name
        if src.exists() and (not dst.exists() or not filecmp.cmp(src, dst, shallow=True)):
            shutil.copy2(src, dst)
            copied.append(name)
    for d in arma_dir.iterdir():
        if not d.is_dir() or d.name.lower() in NOT_LINKED:
            continue
        link = root / d.name
        if _is_junction(link) and link.exists():  # exists() follows the junction: target still there
            continue
        if link.exists() and not _is_junction(link):
            continue  # a real folder of ours; leave it
        if _is_junction(link):
            _remove_junction(link)
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(d)], check=True, capture_output=True)
        linked.append(d.name)
    return {"root": str(root), "copied": copied, "linked": linked}


def _remove_junction(link: Path) -> None:
    # rmdir removes the junction itself, never the target's contents.
    subprocess.run(["cmd", "/c", "rmdir", str(link)], check=True, capture_output=True)


def remove(root: Path) -> None:
    """Remove the server root safely: unlink its junctions (never following them), verify that no link of
    any kind remains anywhere in the tree, and only then delete what is left (our copied files)."""
    if not root.exists():
        return
    if not (root / COPIED_FILES[0]).exists() or not (root / "MPMissions").is_dir():
        raise RuntimeError(f"refusing to remove {root}: it does not look like a harness server root")
    for child in root.iterdir():
        if _is_junction(child):
            _remove_junction(child)
    remaining = [p for p in root.rglob("*") if p.is_symlink() or _is_junction(p)]
    if remaining:
        raise RuntimeError(f"refusing to remove {root}: links remain ({remaining[:3]}); remove them by hand")
    shutil.rmtree(root)
