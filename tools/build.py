"""Build the @brmh mod: Rust extension + HEMTT addon + Python bridge, assembled into the harness home.

    python tools/build.py            # build and deploy to %LOCALAPPDATA%/arma-harness/mods/@brmh
    python tools/build.py --check    # also run all offline checks (cargo test, hemtt check, bridge tests, pytest)

The game locks a loaded extension DLL and the PBOs: stop runs (arma-harness stop) before deploying.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = Path(os.environ.get("BRMH_HOME") or Path(os.environ.get("LOCALAPPDATA", "")) / "arma-harness")
ARMA = Path(os.environ.get("ARMA3_DIR") or r"C:\Program Files (x86)\Steam\steamapps\common\Arma 3")
EMBEDDED_PY = ARMA / "!Workshop" / "@Pythia" / "python-310-embed-amd64" / "python.exe"


def find_hemtt() -> Path:
    """$HEMTT, then hemtt on PATH, then the newest <harness home>/tools/hemtt-*/hemtt.exe."""
    if os.environ.get("HEMTT"):
        return Path(os.environ["HEMTT"])
    on_path = shutil.which("hemtt")
    if on_path:
        return Path(on_path)
    local = sorted((HOME / "tools").glob("hemtt-*/hemtt.exe"))
    if local:
        return local[-1]
    sys.exit("HEMTT not found: install it (https://hemtt.dev), put it on PATH, or set HEMTT=<path to hemtt.exe>")


def run(cmd: list, cwd: Path = REPO) -> None:
    print(f"$ {' '.join(map(str, cmd))}", flush=True)
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)


def build_extension() -> None:
    run(["cargo", "build", "--release"], cwd=REPO / "brmh_ext")
    shutil.copy2(REPO / "brmh_ext" / "target" / "release" / "brmh.dll", REPO / "brmh_x64.dll")


def build_addon() -> None:
    run([find_hemtt(), "build"])


MOD_MARKER = 'name = "BRMH Harness'


def is_harness_build(path: Path) -> bool:
    """True only for a folder this script produced: a real directory (not a link or junction) whose
    mod.cpp names the harness. Nothing else is ever deleted or replaced by deploy()."""
    mod_cpp = path / "mod.cpp"
    return (path.is_dir() and not path.is_symlink() and not path.is_junction() and mod_cpp.is_file()
            and MOD_MARKER in mod_cpp.read_text(encoding="utf-8", errors="replace"))


def remove_build(path: Path) -> None:
    if not is_harness_build(path):
        sys.exit(f"refusing to delete {path}: not a harness build folder (check it by hand)")
    shutil.rmtree(path)


def deploy() -> bool:
    """Deploy <home>/mods/@brmh, keeping the replaced build as @brmh.prev.

    All-or-nothing: the current mod is renamed aside in one step, which Windows refuses while a game has
    its files open, so a mod in use is never touched. Only verified harness builds are ever deleted (the
    older @brmh.prev and leftover staging). Returns False if the mod is in use."""
    src = REPO / ".hemttout" / "build"
    dst = HOME / "mods" / "@brmh"
    staging, prev = dst.with_name("@brmh.new"), dst.with_name("@brmh.prev")
    if dst.exists() and not is_harness_build(dst):
        sys.exit(f"refusing to replace {dst}: it is not a harness build folder (check it by hand)")
    if staging.exists():
        remove_build(staging)
    shutil.copytree(src, staging, ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"))
    if dst.exists():
        if prev.exists():
            remove_build(prev)
        try:
            dst.rename(prev)
        except PermissionError:
            remove_build(staging)
            print(f"NOT DEPLOYED: {dst} is in use by a running game (close it, or `arma-harness stop`)")
            return False
    staging.rename(dst)
    print(f"deployed {dst} (previous build kept as {prev.name})")
    return True


def checks() -> None:
    run(["cargo", "test", "--release"], cwd=REPO / "brmh_ext")
    run([find_hemtt(), "check"])
    if EMBEDDED_PY.exists():
        run([EMBEDDED_PY, "-I", REPO / "python" / "tests" / "test_bridge.py"])
    else:
        print(f"skipping bridge tests: {EMBEDDED_PY} not found")
    venv_py = REPO / "host" / ".venv" / "Scripts" / "python.exe"
    py = venv_py if venv_py.exists() else Path(sys.executable)
    run([py, "-m", "pytest", "-q"], cwd=REPO / "host")
    run([py, "-m", "ruff", "check", "src", "tests"], cwd=REPO / "host")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="run offline checks after building")
    ap.add_argument("--no-deploy", action="store_true")
    a = ap.parse_args()
    build_extension()
    build_addon()
    deployed = a.no_deploy or deploy()
    if a.check:
        checks()
    if not deployed:
        sys.exit(1)


if __name__ == "__main__":
    main()
