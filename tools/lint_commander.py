"""Lint commander mode's game side (host/src/arma_harness/adapters/commander/*.sqf) with HEMTT.

The host sends that code to the game itself, so it isn't in any addon HEMTT would check. This puts a copy in a
throwaway HEMTT project in a temp folder, with the repo's own lint settings, runs `hemtt check`, and fails on any
error or warning, or on any of HEMTT's hints.

    python tools/lint_commander.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import REPO, find_hemtt

SOURCE = REPO / "host" / "src" / "arma_harness" / "adapters" / "commander"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="brmh_lint_") as tmp:
        project = Path(tmp)
        (project / ".hemtt").mkdir()
        shutil.copy(REPO / ".hemtt" / "lints.toml", project / ".hemtt" / "lints.toml")
        (project / ".hemtt" / "project.toml").write_text(
            'name = "Commander lint"\nprefix = "brmhlint"\nmainprefix = "x"\n\n'
            "[version]\nmajor = 0\nminor = 1\npatch = 0\ngit_hash = 0\n", encoding="utf-8")
        addon = project / "addons" / "cmd"
        (addon / "functions").mkdir(parents=True)
        (addon / "$PBOPREFIX$").write_text("x\\brmhlint\\addons\\cmd", encoding="utf-8")
        (addon / "config.cpp").write_text(
            "class CfgPatches {\n\tclass brmhlint_cmd {\n\t\tunits[] = {};\n\t\tweapons[] = {};\n"
            "\t\trequiredVersion = 2.18;\n\t\trequiredAddons[] = {};\n\t};\n};\n", encoding="utf-8")
        files = sorted(SOURCE.glob("*.sqf"))
        for source in files:
            shutil.copy(source, addon / "functions" / source.name)
        done = subprocess.run([str(find_hemtt()), "check"], check=False, cwd=project, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        out = ANSI.sub("", done.stdout + done.stderr)
    findings = re.findall(r"^(?:error|warning|help)\[[\w-]+\]: .*$", out, flags=re.MULTILINE)
    if done.returncode != 0 or findings:
        print(out)
        print(f"FAIL: {len(findings)} findings in {len(files)} files")
        return 1
    print(f"ok: {len(files)} files, no findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
