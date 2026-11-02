"""Audit log: every SQF execution request, append-only JSON lines (spec S4)."""
from __future__ import annotations

import json
import time
from pathlib import Path


class Audit:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, **fields) -> None:
        fields.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        code = fields.get("code")
        if isinstance(code, str) and len(code) > 4000:
            fields["code"] = code[:4000] + f"...<{len(code)} chars>"
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fields, default=str) + "\n")
