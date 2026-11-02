"""Mission staging: copy a mission folder into the server root, with dev-only tweaks in the copy.

Why a copy: the engine locks every file it reads until the process exits (a junction to the live
folder would block the author's editor saves), and the dedicated server runs a packed snapshot anyway.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import rap

IGNORED = shutil.ignore_patterns(".git", ".docs", ".vscode", ".idea", "*.md", "__pycache__")
MARKER = "// --- arma-harness (staged copy only) ---"


def read_sqm_text(sqm: Path) -> str:
    data = sqm.read_bytes()
    if data[:4] == b"\0raP":
        return rap.derapify(data)
    return data.decode("utf-8", "replace")


def inspect(source: Path) -> dict:
    """What the harness needs to know about a mission before running it."""
    sqm = source / "mission.sqm"
    text = read_sqm_text(sqm) if sqm.exists() else ""
    desc = source / "description.ext"
    desc_text = desc.read_text("utf-8", "replace") if desc.exists() else ""
    return {
        "name": source.name,
        "world": source.name.rsplit(".", 1)[-1] if "." in source.name else "",
        "binarized": sqm.exists() and sqm.read_bytes()[:4] == b"\0raP",
        "playable": len(re.findall(r"isPlayable\s*=\s*1", text)),
        "hc_slots": text.count('type="HeadlessClient_F"'),
        "respawn": (re.search(r'respawn\s*=\s*"?(\w+)"?', desc_text) or [None, None])[1],
    }


class StagingError(RuntimeError):
    pass


def _remove_staged_copy(dest: Path, mpmissions: Path) -> None:
    """Delete an earlier staged copy, and nothing else: it must sit directly in ``mpmissions``, be a real
    folder (not a link or junction), contain no links, and carry the staging marker we append."""
    desc = dest / "description.ext"
    checks = {
        "inside MPMissions": dest.resolve().parent == mpmissions.resolve(),
        "a real folder": dest.is_dir() and not dest.is_symlink() and not dest.is_junction(),
        "staged by the harness": desc.is_file() and MARKER in desc.read_text("utf-8", "replace"),
        "free of links": not any(p.is_symlink() or p.is_junction() for p in dest.rglob("*")),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise StagingError(f"refusing to replace {dest}: not {', '.join(failed)}; check it by hand")
    shutil.rmtree(dest)


def stage(source: Path, mpmissions: Path, *, skip_lobby: bool = True, allow_recompile: bool = True,
          extra: list[str] | None = None) -> Path:
    """Copy ``source`` to ``mpmissions/<name>`` (replacing an older copy) and append dev settings."""
    if not (source / "mission.sqm").exists():
        raise FileNotFoundError(f"{source} has no mission.sqm")
    dest = mpmissions / source.name
    if dest.exists():
        _remove_staged_copy(dest, mpmissions)
    shutil.copytree(source, dest, ignore=IGNORED)
    lines = [MARKER]
    if skip_lobby:
        # Rendering clients join straight into the world: no role selection, no briefing map.
        lines += ["skipLobby = 1;", "briefing = 0;"]
    if allow_recompile:
        lines.append("allowFunctionsRecompile = 1;")
    # Note: persistent = 1 only keeps a mission alive after the last player leaves with base/instant
    # respawn. We do not inject respawn settings: that would change gameplay in the copy.
    lines += extra or []
    desc = dest / "description.ext"
    existing = desc.read_text("utf-8", "replace") if desc.exists() else ""
    desc.write_text(existing.rstrip() + "\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return dest
