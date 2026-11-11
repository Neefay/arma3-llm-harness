"""Lint the command library's SQF (host/src/arma_harness/library/) with HEMTT, as lint_commander.py does the
commander's: the host sends that code to the game itself, so it isn't in any addon HEMTT would check.

    python tools/lint_library.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import REPO
from lint_commander import lint

if __name__ == "__main__":
    sys.exit(lint([REPO / "host" / "src" / "arma_harness" / "library"], "Library"))
