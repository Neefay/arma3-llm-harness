"""The commander's records: basic text files, one folder per run and side. Reached only through its tools."""
from __future__ import annotations

import json
import os
from pathlib import Path


class Records:
    def __init__(self, folder: Path, truth_file: Path | None = None):
        self.folder = folder
        self.truth_file = truth_file or folder.parent / "truth.jsonl"
        folder.mkdir(parents=True, exist_ok=True)

    def append(self, name: str, row: dict) -> None:
        with (self.folder / f"{name}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def read(self, name: str) -> list[dict]:
        file = self.folder / f"{name}.jsonl"
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]

    def truth(self, row: dict) -> None:
        with self.truth_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def read_truth(self) -> list[dict]:
        if not self.truth_file.exists():
            return []
        return [json.loads(line) for line in self.truth_file.read_text(encoding="utf-8").splitlines() if line.strip()]

    def kill(self, row: dict) -> None:
        with (self.truth_file.parent / "kills.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def read_kills(self) -> list[dict]:
        file = self.truth_file.parent / "kills.jsonl"
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]

    def notes(self) -> str:
        file = self.folder / "notes.md"
        return file.read_text(encoding="utf-8") if file.exists() else ""

    def set_notes(self, text: str) -> None:
        (self.folder / "notes.md").write_text(text, encoding="utf-8")

    def load_state(self) -> dict:
        file = self.folder / "state.json"
        return json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}

    def save_state(self, state: dict) -> None:
        file = self.folder / "state.json"
        tmp = file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, file)

    def operator_log(self, text: str) -> None:
        """Engine and harness details the commander must never see."""
        with (self.folder / "operator.log").open("a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
