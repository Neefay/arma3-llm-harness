"""Operator side: setting up, watching and reviewing a battle. Never available to the commander."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..adapters import load_sqf
from ..config import Home
from ..harness import Harness, HarnessError
from . import scenario as scenario_mod
from .orders import format_time, parse_grid
from .records import Records
from .runtime import Runtime

SERVER_NAME = "commander"
# ToolSearch loads the commander's own tools. A deny rule can't remove advisor, but it can't reach game data.
HARMLESS_TOOLS = {"ToolSearch", "DeferredToolPlaceholder", "advisor"}
# Named one by one because the client offers whatever isn't denied, and that list grows. A live check of what a session
# actually received found SendMessage, for one, which could ask another local session what's really happening.
DENIED_TOOLS = [
    "Bash", "PowerShell", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "NotebookEdit", "Agent",
    "Task", "TaskStop", "Skill", "Workflow", "SendMessage", "ListAgents", "RemoteTrigger", "CronCreate", "CronDelete",
    "CronList", "ScheduleWakeup", "PushNotification", "Monitor", "Artifact", "ArtifactComments", "ArtifactData",
    "DesignSync", "ReportFindings", "EnterWorktree", "ExitWorktree", "EnterPlanMode", "ExitPlanMode", "SendFeedback",
    "AskUserQuestion", "ListMcpResourcesTool", "ReadMcpResourceTool", "ReadMcpResourceDirTool", "mcp__arma",
    "mcp__MCP_DOCKER", "mcp__taskboard", "mcp__plugin_a3ref_a3ref", "mcp__claude_ai_Claude_Docs",
    "mcp__claude_ai_Gmail", "mcp__claude_ai_Google_Calendar", "mcp__claude_ai_Google_Drive", "mcp__claude-vscode",
]


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


def start(path: str, mode: str | None = None, harness: Harness | None = None, watch: bool = False) -> dict:
    """Boot the scenario's mission if needed, put the stations on the net, and prepare the commander's records."""
    h = harness or Harness()
    raw = _read_raw(path)
    if mode:
        raw["mid_turn_messages"] = mode
    scenario = scenario_mod.build(raw)
    h.forget_dead_run()
    state = h.state()
    if state is not None and state.mission != scenario.mission:
        raise HarnessError(f"run {state.run_id} is {state.mission!r}, and this scenario needs {scenario.mission!r}. "
                           "Stop it first (arma-harness commander stop).")
    # Booting takes a while, and a session opened meanwhile mustn't find the last battle and think it's this one.
    _current_file(h.home).unlink(missing_ok=True)
    if state is None:
        h.start(mission=scenario.mission)
        state = h.state()
    world = _result(h.exec("[worldSize, mapGridPosition [3450, 3050, 0]]", "server", timeout=10))
    world_size, sample = world
    if sample != "034030":
        raise HarnessError(f"this world's grid isn't a plain 100 m grid ({sample!r}), which isn't supported yet")
    _result(h.exec(load_sqf("commander_boot.sqf"), "server", timeout=20, strip=False))
    # A repeat start reuses the running game, so clear the previous attempt's soldiers first.
    _result(h.exec("call brmh_cmd_fnc_clearAll", "server", timeout=10))
    for station in scenario.stations.values():
        at, _ = parse_grid(station["at"], world_size)
        _result(h.exec('[_this # 0, [west, east] select (_this # 1 isEqualTo "east"), _this # 2, _this # 3, _this # 4] '
                       "call brmh_cmd_fnc_enroll", "server", timeout=10,
                       args=[station["callsign"], scenario.side, station["units"], station["class"], at]))
        if station["medics"]:
            _result(h.exec("_this call brmh_cmd_fnc_makeMedics", "server", timeout=10,
                           args=[station["callsign"], station["medics"]]))
    if scenario.medical:
        _result(h.exec("{brmh_cmd_careTimes set [_x # 0, _x # 1]} forEach _this; true", "server", timeout=10,
                       args=[[key, value] for key, value in scenario.medical.items()]))
        if "wake_chance" in scenario.medical:
            code = 'missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", _this # 0, true]; true'
            _result(h.exec(code, "server", timeout=10, args=[scenario.medical["wake_chance"]]))
    _spawn_enemies(h, scenario, world_size)
    buildings = _list_buildings(h, scenario, world_size)
    _result(h.exec("brmh_cmd_buildings = createHashMapFromArray _this; true", "server", timeout=10,
                   args=[[building["id"], building["pos"]] for building in buildings]))
    vehicles = _spawn_vehicles(h, scenario, world_size)
    for station in scenario.stations.values():
        for vehicle_id, seat in station["crew"].items():
            if not _result(h.exec("_this call brmh_cmd_fnc_crew", "server", timeout=10,
                                  args=[station["callsign"], vehicle_id, seat])):
                raise HarnessError(f"{station['callsign']} couldn't crew {vehicle_id} as {seat}")
    attempt = _next_attempt(h.home, state.run_id)
    records_folder = h.home.runs / state.run_id / f"commander-{attempt}" / scenario.side
    records_folder.mkdir(parents=True, exist_ok=True)
    # What the battle was, kept with its records so a replay still works after later battles have replaced current.json.
    (records_folder.parent / "battle.json").write_text(json.dumps(
        {"scenario": raw, "buildings": buildings, "vehicles": vehicles, "world_size": world_size, "run": state.run_id,
         "attempt": attempt}, indent=2), encoding="utf-8")
    current = {"run": state.run_id, "attempt": attempt, "folder": str(records_folder), "scenario": raw,
               "world_size": world_size, "buildings": buildings, "vehicles": vehicles}
    _current_file(h.home).write_text(json.dumps(current, indent=2), encoding="utf-8")
    workspace = write_workspace(h.home)
    observer = None
    if watch and not any(proc.kind == "client" for proc in state.procs):
        observer = h.client_start()
    return {"observer": observer, "scenario": scenario.name, "mode": scenario.mid_turn_messages, "run": state.run_id,
            "attempt": attempt,
            "records": str(records_folder), "workspace": str(workspace), "launch": launch_command(workspace),
            "then": 'Accept the prompts, then type: start'}


def _list_buildings(h: Harness, scenario: scenario_mod.Scenario, world_size: float) -> list[dict]:
    """Numbers the enterable buildings in the area of operations, west to east. This is map knowledge: which
    buildings exist, never who's in them."""
    if not scenario.ao:
        return []
    at, _ = parse_grid(scenario.ao["at"], world_size)
    _wait_for_buildings(h, at, scenario.ao["radius"])
    rows = _result(h.exec("_this call brmh_cmd_fnc_listBuildings", "server", timeout=15,
                          args=[at, scenario.ao["radius"]]))
    rows = sorted(rows, key=lambda row: (round(row[0] / 50), row[1]))
    return [{"id": f"B{index}", "pos": [row[0], row[1]], "at": f"{row[2][:3]} {row[2][3:]}", "name": row[3],
             "positions": row[4], "width": row[5], "length": row[6], "dir": row[7]}
            for index, row in enumerate(rows, start=1)]


def _spawn_vehicles(h: Harness, scenario: scenario_mod.Scenario, world_size: float) -> list[dict]:
    """Places the scenario's guns and vehicles. The commander only starts out knowing about the ones marked known."""
    placed = []
    for vehicle in scenario.vehicles:
        at, grid = parse_grid(vehicle["at"], world_size)
        ammo = [[word.upper(), rounds] for word, rounds in vehicle["ammo"].items()]
        name = _result(h.exec("_this call brmh_cmd_fnc_spawnVehicle", "server", timeout=10,
                              args=[vehicle["id"], vehicle["class"], at, ammo]))
        if vehicle["medical"]:
            code = '(brmh_cmd_vehicles get _this # 0) setVariable ["ace_medical_isMedicalVehicle", true, true]; true'
            _result(h.exec(code, "server", timeout=10, args=[vehicle["id"]]))
        placed.append({"id": vehicle["id"], "name": name, "at": grid, "known": vehicle["known"]})
    return placed


def _spawn_enemies(h: Harness, scenario: scenario_mod.Scenario, world_size: float) -> None:
    for enemy in scenario.enemies:
        at, _ = parse_grid(enemy["at"], world_size)
        if enemy["mode"] == "garrison":
            _wait_for_buildings(h, at, enemy["radius"])
        spawned = _result(h.exec('[_this # 0, [east, west] select (_this # 1 isEqualTo "west"), _this # 2, _this # 3, '
                                 "_this # 4, _this # 5, _this # 6] call brmh_cmd_fnc_spawnEnemy", "server", timeout=10,
                                 args=[enemy["id"], enemy["side"], enemy["units"], enemy["class"], at, enemy["mode"],
                                       enemy["radius"]]))
        if spawned != enemy["units"]:
            raise HarnessError(f"enemy {enemy['id']}: spawned {spawned} of {enemy['units']}")


def _wait_for_buildings(h: Harness, at: list[float], radius: float, timeout: float = 30) -> None:
    """A mission can still be building its village when a fresh run gets here."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = _result(h.exec('count (nearestObjects [(_this # 0) + [0], ["House"], _this # 1] select { '
                               "count (_x buildingPos -1) > 0 })", "server", timeout=10, args=[at, radius]))
        if found:
            return
        time.sleep(2)
    raise HarnessError(f"no enterable buildings within {radius} m of {at} to garrison")


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
                   world_size=current["world_size"], buildings=current.get("buildings"),
                   vehicles=current.get("vehicles"))


def is_current(runtime: Runtime, home: Home | None = None) -> bool:
    """Whether this is still the battle that `commander start` last set up."""
    file = _current_file(home or Home())
    try:
        return Path(json.loads(file.read_text(encoding="utf-8"))["folder"]) == runtime.records.folder
    except FileNotFoundError:
        return False
    except ValueError:  # caught halfway through being written, which says nothing
        return True


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
        if "mission_end" in row:
            rows.append((row["t"], f"END    {row['mission_end']}"))
        elif "objective_complete" in row:
            rows.append((row["t"], f"GOAL   {row['text']}"))
        else:
            rows.append((row["t"], f"EVENT  {row['scenario_event']}"))
    stations, dead = _stations(records), set()
    for row in records.read_truth():
        parts = []
        for group in row["groups"]:
            if group["group"] not in stations:
                continue
            if group.get("pos"):
                dead.discard(group["group"])
                able = group.get("able", group.get("alive", 0))  # older truth records call it "alive"
                parts.append(f"{group['group']} {able} alive at {[round(c) for c in group['pos']]}")
            elif group["group"] not in dead:  # once is enough: a wiped-out group is otherwise missing from the review
                dead.add(group["group"])
                parts.append(f"{group['group']} 0 alive")
        if parts:
            rows.append((row["t"], "TRUTH  " + "; ".join(parts)))
    rows.sort(key=lambda r: r[0])
    return "\n".join(f"{format_time(t)}  {text}" for t, text in rows)


def _stations(records: Records) -> set[str]:
    senders = {r["from"] for r in records.read("radio")} | {r["to"] for r in records.read("radio")}
    return senders - {"HQ"}


def tools_received(rows: list[dict]) -> tuple[set[str], set[str]] | None:
    """From a session transcript: the (loaded, deferred) tools the client really offered, or None if not recorded."""
    loaded: set[str] = set()
    deferred: set[str] = set()
    shapes = [row for row in rows if row.get("type") == "api-request-shape"]
    if not shapes:
        return None

    def collect(value) -> None:
        if isinstance(value, dict):
            for tool in value["tools"] if isinstance(value.get("tools"), list) else []:
                if isinstance(tool, dict) and tool.get("name"):
                    loaded.add(tool["name"])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(shapes)
    for row in rows:
        attachment = row.get("attachment") or {}
        if attachment.get("type") == "deferred_tools_delta":
            deferred |= set(attachment.get("addedNames") or [])
            deferred -= set(attachment.get("removedNames") or [])
    return loaded, deferred


def judge_lockdown(received: tuple[set[str], set[str]] | None) -> dict:
    """Compare what a session received with the commander's allowlist. Unreadable counts as failure, not success."""
    from .server import TOOL_NAMES  # the server imports this module

    if received is None:
        return {"ok": False, "error": "the transcript has no record of the tools sent, so nothing was verified. The "
                                      "client's transcript format may have changed."}
    loaded, deferred = received
    offered = loaded | deferred
    expected = {f"mcp__{SERVER_NAME}__{name}" for name in TOOL_NAMES}
    unexpected = sorted(offered - expected - HARMLESS_TOOLS)
    missing = sorted(expected - offered)
    return {"ok": not unexpected and not missing, "unexpected": unexpected, "missing": missing,
            "commander_tools": len(expected & offered), "other_tools_allowed": sorted(offered & HARMLESS_TOOLS)}


def check_lockdown(home: Home | None = None) -> dict:
    """Start a real one-shot session in the workspace and read which tools the client actually offered it. Asking
    the model proves little: a well-behaved one declines whether it's blocked or not. Uses one small model call."""
    home = home or Home()
    workspace = write_workspace(home)
    claude = shutil.which("claude")
    if claude is None:
        raise HarnessError("claude isn't on the PATH")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    command = [claude, "-p", "Reply with the single word: ok", "--model", "haiku", "--output-format", "json"]
    done = subprocess.run(command, cwd=workspace, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          encoding="utf-8", timeout=180, check=False)
    try:
        session = json.loads(done.stdout)["session_id"]
    except (ValueError, KeyError, TypeError):
        return {"ok": False, "error": f"couldn't read the session's id: {done.stdout[-300:]} {done.stderr[-300:]}"}
    files = list((Path.home() / ".claude" / "projects").glob(f"*/{session}.jsonl"))
    if not files:
        return {"ok": False, "error": f"no transcript found for session {session}"}
    rows = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines() if line.strip()]
    return {**judge_lockdown(tools_received(rows)), "workspace": str(workspace), "note": (
        "This session ran without the channel flag, so an interactive session's list could differ. Rerun after any "
        "new client version, plugin or connector, because the deny list names tools one by one.")}


def stop(harness: Harness | None = None) -> dict:
    h = harness or Harness()
    _current_file(h.home).unlink(missing_ok=True)
    workspace = _commander_home(h.home) / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    return h.stop()
