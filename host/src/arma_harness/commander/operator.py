"""Operator side: setting up, watching and reviewing a battle. Never available to the commander."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from ..adapters import load_sqf
from ..config import Home
from ..harness import Harness, HarnessError
from . import scenario as scenario_mod
from .orders import format_time, parse_grid
from .records import Records
from .runtime import Runtime

SERVER_NAME = "commander"
DENIED_TOOLS = ["Bash", "PowerShell", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "NotebookEdit",
                "Agent", "Task", "Skill", "mcp__arma", "mcp__MCP_DOCKER", "mcp__plugin_a3ref_a3ref"]


def _commander_home(home: Home) -> Path:
    folder = home.root / "commander"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _current_file(home: Home) -> Path:
    return _commander_home(home) / "current.json"


def write_workspace(home: Home | None = None) -> Path:
    """The folder the commander session runs from: its MCP server and tool lockdown, nothing else."""
    home = home or Home()
    folder = _commander_home(home) / "workspace"
    (folder / ".claude").mkdir(parents=True, exist_ok=True)
    (folder / ".mcp.json").write_text(json.dumps({"mcpServers": {SERVER_NAME: {
        "command": Path(sys.executable).as_posix(), "args": ["-m", "arma_harness.commander.server"],
    }}}, indent=2) + "\n", encoding="utf-8")
    (folder / ".claude" / "settings.json").write_text(json.dumps({"permissions": {
        "defaultMode": "dontAsk", "allow": [f"mcp__{SERVER_NAME}"], "deny": DENIED_TOOLS,
    }}, indent=2) + "\n", encoding="utf-8")
    (folder / "CLAUDE.md").unlink(missing_ok=True)  # written by earlier versions, and the Read deny blocks it anyway
    return folder


def launch_command(folder: Path) -> str:
    return (f'cd "{folder}"\n'
            f"claude --dangerously-load-development-channels server:{SERVER_NAME}")


def start(path: str, mode: str | None = None, harness: Harness | None = None) -> dict:
    """Boot the scenario's mission if needed, put the stations on the net, and prepare the commander's records."""
    h = harness or Harness()
    raw = _read_raw(path)
    if mode:
        raw["mid_turn_messages"] = mode
    scenario = scenario_mod.build(raw)
    state = h.state()
    if state is None:
        h.start(mission=scenario.mission)
        state = h.state()
    elif state.mission != scenario.mission:
        raise HarnessError(f"run {state.run_id} is {state.mission!r}, and this scenario needs {scenario.mission!r}. "
                           "Stop it first (arma-harness commander stop).")
    world = _result(h.exec("[worldSize, mapGridPosition [3450, 3050, 0]]", "server", timeout=10))
    world_size, sample = world
    if sample != "034030":
        raise HarnessError(f"this world's grid isn't a plain 100 m grid ({sample!r}), which isn't supported yet")
    _result(h.exec(load_sqf("commander_boot.sqf"), "server", timeout=20, strip=False))
    # A repeat start reuses the running game, so clear the previous attempt's soldiers first.
    _result(h.exec("{ [_x] call brmh_cmd_fnc_deleteStation } forEach (keys brmh_cmd_stations); "
                   "brmh_cmd_stations = createHashMap; true", "server", timeout=10))
    for station in scenario.stations.values():
        at, _ = parse_grid(station["at"], world_size)
        _result(h.exec('[_this # 0, [west, east] select (_this # 1 isEqualTo "east"), _this # 2, _this # 3, _this # 4] '
                       "call brmh_cmd_fnc_enroll", "server", timeout=10,
                       args=[station["callsign"], scenario.side, station["units"], station["class"], at]))
    attempt = _next_attempt(h.home, state.run_id)
    records_folder = h.home.runs / state.run_id / f"commander-{attempt}" / scenario.side
    records_folder.mkdir(parents=True, exist_ok=True)
    current = {"run": state.run_id, "attempt": attempt, "folder": str(records_folder), "scenario": raw,
               "world_size": world_size}
    _current_file(h.home).write_text(json.dumps(current, indent=2), encoding="utf-8")
    workspace = write_workspace(h.home)
    return {"scenario": scenario.name, "mode": scenario.mid_turn_messages, "run": state.run_id, "attempt": attempt,
            "records": str(records_folder), "workspace": str(workspace), "launch": launch_command(workspace),
            "then": 'Accept the prompts, then type: start'}


def _read_raw(path: str) -> dict:
    import yaml

    file = Path(path)
    if not file.exists():
        file = scenario_mod.SCENARIO_DIR / f"{path}.yaml"
    return yaml.safe_load(file.read_text(encoding="utf-8"))


def _next_attempt(home: Home, run_id: str) -> int:
    existing = [p.name for p in (home.runs / run_id).glob("commander-*")]
    return max((int(name.split("-")[1]) for name in existing), default=0) + 1


def _result(response: dict):
    results = response.get("results") or []
    if not response.get("ok") or not results:
        raise HarnessError(f"game setup failed: {response}")
    return results[0].get("r")


class HarnessGame:
    """The narrow view of the game that the runtime gets."""

    def __init__(self, harness: Harness):
        self.harness = harness

    def events(self, since: int, wait: float) -> dict:
        return self.harness.bridge().events(since=since, wait=wait, limit=2000)

    def exec(self, code: str, args: list) -> dict:
        return self.harness.exec(code, "server", timeout=5, args=args, strip=False)


def load_current(deliver) -> Runtime:
    """Build the runtime for the battle set up by the latest `commander start`."""
    h = Harness()
    file = _current_file(h.home)
    if not file.exists():
        raise HarnessError("no commander scenario is set up: run arma-harness commander start <scenario>")
    current = json.loads(file.read_text(encoding="utf-8"))
    return Runtime(HarnessGame(h), scenario_mod.build(current["scenario"]), Records(Path(current["folder"])), deliver,
                   world_size=current["world_size"])


def _load_records(home: Home) -> tuple[dict, Records]:
    file = _current_file(home)
    if not file.exists():
        raise HarnessError("no commander scenario is set up")
    current = json.loads(file.read_text(encoding="utf-8"))
    return current, Records(Path(current["folder"]))


def status(home: Home | None = None) -> dict:
    current, records = _load_records(home or Home())
    state = records.load_state()
    wake = state.get("wake") or {}
    turns = records.read("turns")
    return {
        "scenario": current["scenario"]["name"], "run": current["run"], "attempt": current["attempt"],
        "records": current["folder"], "started": state.get("t0") is not None, "ended": state.get("ended") or None,
        "mode": wake.get("mode"), "turn": state.get("turn", 0), "in_turn": wake.get("in_turn", False),
        "active_timers": list((wake.get("timers") or {}).values()),
        "no_wake_scheduled": bool(state.get("t0") is not None and not state.get("ended") and not wake.get("in_turn")
                                  and not wake.get("timers")),
        "messages_only": wake.get("messages_only", False), "turns_logged": len(turns),
        "turns_assumed_over": sum(1 for t in turns if str(t.get("note", "")).startswith("assumed over")),
    }


def aar(home: Home | None = None) -> str:
    """Everything on one timeline: what was said, what the commander did, and where everyone really was."""
    _, records = _load_records(home or Home())
    rows = []
    for row in records.read("radio"):
        rows.append((row["t"], f"RADIO  {row['from']} -> {row['to']}: {row['text']}"))
    for row in records.read("turns"):
        rows.append((row["start"], f"TURN   {row['turn']} woke on {row['woke_on']}"))
        rows.append((row["end"], f"TURN   {row['turn']} ended after {row['duration']} s: {row.get('note', '')}"))
    for row in records.read("schedule"):
        words = f"cancelled {row['id']}" if "cancelled" in row else f"{row['id']} for {format_time(row['due'])}"
        rows.append((row["t"], f"TIMER  {words}"))
    for row in records.read("radio_events"):
        rows.append((row["t"], f"END    {row['mission_end']}"))
    for row in records.read_truth():
        where = "; ".join(f"{g['group']} {g['alive']} alive at {[round(c) for c in g['pos']]}"
                          for g in row["groups"] if g.get("pos") and g["group"] in _stations(records))
        if where:
            rows.append((row["t"], f"TRUTH  {where}"))
    rows.sort(key=lambda r: r[0])
    return "\n".join(f"{format_time(t)}  {text}" for t, text in rows)


def _stations(records: Records) -> set[str]:
    senders = {r["from"] for r in records.read("radio")} | {r["to"] for r in records.read("radio")}
    return senders - {"HQ"}


def stop(harness: Harness | None = None) -> dict:
    h = harness or Harness()
    _current_file(h.home).unlink(missing_ok=True)
    workspace = _commander_home(h.home) / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    return h.stop()
