"""After-action review: one self-contained HTML page replaying a battle from its records, belief against truth.

For people only. The commander has no tool that reaches any of this. The page holds everything it needs, so it can be
opened long after the run's other files are gone. Its map of what the commander believed is built only from words the
commander received, by reading the same radio text it read.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter
from datetime import datetime
from importlib import resources
from pathlib import Path

from ..config import Home
from . import scenario as scenario_mod
from .operator import judge_lockdown, tools_received
from .orders import Invalid, parse_grid
from .records import Records
from .runtime import RECORD_AFTER_END_S

DATA_SLOT = "/*BATTLE_DATA*/"
_POSITION = re.compile(r"(?:^|\bat |, )grid (\d{3} \d{3})", re.IGNORECASE)
_CHECKED = re.compile(r"^(B\d+) checked\b")
_TOOL = "mcp__commander__commander_"
SHELL_KILL_M = 60  # a shell landing this close, just before a death, is what did it
SHELL_KILL_S = 5
DANGER_CLOSE_M = 150  # a commander firing this near a station's reported place knows what it's risking
MOVED_M = 100
_ACTIONS = {"order", "ask", "schedule", "unschedule", "mark", "unmark", "notes"}


def _able(group: dict) -> int:
    """How many of a group could act. Truth records from before the rename call it "alive", and reviews still read
    those. The review's own output keeps "alive", which its viewer reads."""
    return group.get("able", group.get("alive", 0))


def reported_position(text: str) -> str | None:
    """The sender's own position in a radio message, if it gave one. "Moving to grid 041 034" isn't one."""
    found = _POSITION.findall(text)
    return found[-1] if found else None


def battle_data(folder: Path, commander: dict | None = None) -> dict:
    """Everything the page needs. ``folder`` is a commander's records: <run>/commander-<n>/<side>."""
    records = Records(folder)
    info_file = folder.parent / "battle.json"
    info = json.loads(info_file.read_text(encoding="utf-8")) if info_file.exists() else {}
    scenario = info.get("scenario") or {}
    world_size = info.get("world_size") or 0
    state = records.load_state()
    stations = {s["callsign"]: {"units": s.get("units", 4), "role": s.get("role", "")}
                for s in scenario.get("stations") or []}
    enemies = scenario.get("enemies") or []
    enemy_ids = [enemy["id"] for enemy in enemies]
    wanted = set(stations) | set(enemy_ids)  # leaves out the observer and any groups left from an earlier battle

    ending = next((row for row in records.read("radio_events") if "mission_end" in row), {})
    ended_at = ending.get("t")
    cutoff = None if ended_at is None else ended_at + RECORD_AFTER_END_S

    def in_battle(row: dict) -> bool:
        return cutoff is None or row.get("t", 0) <= cutoff

    frames = [{"t": row["t"], "groups": [_group(g) for g in row.get("groups") or [] if g.get("group") in wanted]}
              for row in _until_clock_restarts(records.read_truth()) if in_battle(row)]
    radio = [_radio(row, world_size) for row in records.read("radio") if in_battle(row)]
    objectives = [row for row in records.read("radio_events") if "objective_complete" in row]
    radio = sorted(radio + [{"t": row["t"], "from": "HQ", "to": "all", "kind": "objective", "precedence": "flash",
                             "text": f"Objective complete: {row['text']}"} for row in objectives],
                   key=lambda row: row["t"])
    markers = _markers(records, scenario, world_size)
    truth = records.read_truth()
    kills = [_kill(row, folder.name) for row in _until_clock_restarts(records.read_kills())
             if in_battle(row) and not _outside_battle(row, truth, wanted)]
    shells = [_shell(row, folder.name) for row in _until_clock_restarts(records.read_shells()) if in_battle(row)]
    missions = [row for row in records.read("fire_missions") if in_battle(row)]
    for kill in kills:
        _judge_kill(kill, shells, missions, frames, radio, set(stations), world_size)
    turns = _turns(records, state, commander)
    orders = [_order(row, info.get("buildings") or [], markers, world_size) for row in records.read("orders")]
    events = [{"t": row["t"], "event": row["scenario_event"]} for row in records.read("radio_events")
              if "scenario_event" in row and in_battle(row)]
    latest = [row["t"] for rows in (frames, radio, kills) for row in rows[-1:]] + [t["start"] for t in turns[-1:]]
    data = {
        "name": str(scenario.get("name", folder.parent.name)).replace("_", " ").capitalize(),
        "scenario": scenario.get("name", folder.parent.name), "seed": info.get("seed"),
        "hidden": scenario_mod.hidden(scenario) if scenario else "", "events": events,
        "text": str(scenario.get("text", "")).strip(),
        "run": info.get("run", folder.parent.parent.name), "attempt": info.get("attempt"),
        "mode": scenario.get("mid_turn_messages"), "ended_at": ended_at,
        # The state file is only saved now and then, so a session closing at the very end can leave it behind.
        "ended": state.get("ended") or ending.get("mission_end"),
        "commander": {key: value for key, value in (commander or {}).items() if key != "turns"},
        "duration": max(latest, default=1), "world_size": world_size,
        "buildings": info.get("buildings") or [], "stations": stations, "enemies": enemy_ids,
        "enemy_total": _strength(frames, enemies), "frames": frames, "kills": kills,
        "radio": radio, "turns": turns, "markers": markers, "orders": orders, "notes": records.notes(),
        "shells": shells, "missions": [_mission(row, shells) for row in missions],
        "objectives_done": [{"t": row["t"], "id": row["objective_complete"], "text": row["text"]}
                            for row in objectives],
    }
    return {**data, "score": scorecard(data)}


def _strength(frames: list[dict], enemies: list[dict]) -> int:
    """How many the enemy fielded, from what the battle's truth record saw of each group at its largest. A crewed gun's
    entry has no "units": its crew is the vehicle's, and the scenario's default of 4 would overstate it."""
    seen: dict[str, int] = {}
    for frame in frames:
        for group in frame["groups"]:
            seen[group["group"]] = max(seen.get(group["group"], 0), _able(group))
    return sum(seen.get(enemy["id"]) or enemy.get("units", 1 if enemy.get("vehicle") else 4) for enemy in enemies)


def outcome(ended: str | None) -> str:
    """The battle's result as one word, for counting: won, failed, time limit, or unfinished."""
    text = str(ended or "")
    if text.startswith("Objective achieved"):
        return "won"
    if text.startswith(("Mission failed", "All stations have been lost")):
        return "failed"
    if text.startswith("Time limit"):
        return "time limit"
    return "unfinished"


def scorecard(data: dict) -> dict:
    """The measures for comparing battles. Marker and position error say how wrong the commander's picture of the
    battle was. The last three serve particular scenarios (docs/COMMANDER_BENCHMARK.md), and are empty elsewhere."""
    frames = data["frames"]
    left = {group["group"]: _able(group) for group in frames[-1]["groups"]} if frames else {}
    friendly_total = sum(station["units"] for station in data["stations"].values())
    enemy_killed = data["enemy_total"] - sum(left.get(name, 0) for name in data["enemies"])
    rounds = sum(shell["friendly"] for shell in data["shells"])
    return {
        "outcome": outcome(data["ended"]), "seed": data.get("seed"),
        "ended": data["ended"] or "Didn't finish", "duration_s": round(data["ended_at"] or data["duration"]),
        "friendly_lost": friendly_total - sum(left.get(name, 0) for name in data["stations"]),
        "friendly_total": friendly_total,
        "enemy_killed": enemy_killed,
        "enemy_total": data["enemy_total"],
        "first_contact_s": next((round(row["t"]) for row in data["radio"]
                                 if row.get("from") != "HQ" and str(row.get("text")).startswith("Contact")), None),
        "turns": len(data["turns"]), "orders": len(data["orders"]),
        "questions": sum(row.get("kind") == "question" for row in data["radio"]),
        "enemy_markers": len({row["id"] for row in data["markers"] if row.get("kind") == "enemy"}),
        "marker_error_m": _marker_error(data), "position_error_m": _position_error(data),
        "rounds_fired": rounds,
        "own_fire_deaths": sum(bool(kill.get("verdict")) for kill in data["kills"]),
        # Any weapon: the guns' shells above, and an aircraft's or a squad's own fire too.
        "friendly_fire_deaths": sum(kill["friendly"] and str(kill.get("killerSide", "")).lower() == str(
            kill.get("side", "")).lower() and kill.get("killer") != kill.get("victim") for kill in data["kills"]),
        "rounds_per_kill": round(rounds / enemy_killed, 1) if rounds and enemy_killed > 0 else None,
        "threat_reported_s": next((round(row["t"]) for row in data["radio"]
                                   if row.get("from") != "HQ" and "Listed as T" in str(row.get("text"))), None),
        **_silence(data),
    }


def _silence(data: dict) -> dict:
    """For a station silenced by the scenario: who, and how long until the commander ordered or asked it anything.
    Speaking to it is the one sure sign it was missed; acting about it through another station isn't counted."""
    event = next((row for row in data.get("events") or [] if row["event"].startswith("kill_station ")), None)
    if event is None:
        return {"silenced": None, "silence_noticed_s": None}
    station = event["event"].split(" ", 1)[1]
    spoken = [row["t"] for row in data["orders"] if row.get("to") == station and row["t"] >= event["t"]]
    spoken += [row["t"] for row in data["radio"]
               if row.get("kind") == "question" and row.get("to") == station and row["t"] >= event["t"]]
    return {"silenced": station, "silence_noticed_s": round(min(spoken) - event["t"]) if spoken else None}


def _position_error(data: dict) -> int | None:
    """On average over the battle, how far a living station was from the last position it reported."""
    reports = [row for row in data["radio"] if row.get("pos")]
    errors = []
    for frame in data["frames"]:
        heard: dict[str, list[float]] = {}
        for row in reports:
            if row["t"] > frame["t"]:
                break
            heard[row["from"]] = row["pos"]
        errors += [math.dist(heard[group["group"]], group["pos"][:2]) for group in frame["groups"]
                   if group["group"] in heard and _able(group) and group["pos"]]
    return round(sum(errors) / len(errors)) if errors else None


def _marker_error(data: dict) -> int | None:
    """On average, how far each enemy marker was, when placed, from the nearest enemy really alive."""
    errors = []
    for marker in data["markers"]:
        if marker.get("kind") != "enemy" or not marker.get("pos"):
            continue
        frame = next((row for row in data["frames"] if row["t"] >= marker["t"]), None)
        soldiers = [unit for group in (frame or {}).get("groups", []) if group["group"] in data["enemies"]
                    for unit in group["units"]]
        if soldiers:
            errors.append(min(math.dist(marker["pos"], unit) for unit in soldiers))
    return round(sum(errors) / len(errors)) if errors else None


def compare(home: Home, battles: list[str] | None = None, scenario: str | None = None, as_csv: bool = False) -> str:
    """Battles side by side, as a table, or as CSV with one row per battle. Each is RUN or RUN:ATTEMPT. By default,
    every finished battle of a scenario: the one named, or the newest battle's."""
    if battles:
        folders = [find_battle(home, *_battle_name(name)) for name in battles]
    else:
        wanted = scenario or _scenario_name(find_battle(home))
        folders = sorted((path.parent for path in home.runs.glob("*/commander-*/*/radio.jsonl")
                          if _scenario_name(path.parent) == wanted), key=_battle_order)
    cards = []
    for folder in folders:
        data = battle_data(folder, commander_session(folder))
        if battles or data["ended"]:
            run, attempt = _battle_order(folder)
            cards.append((f"{run}:{attempt}", data["commander"].get("model") or "Scripted", data))
    if not cards:
        raise ValueError("no finished battle to compare")
    if as_csv:
        return _csv(cards)
    rows = _comparison(cards)
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
    return "\n".join("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
                     for row in rows)


def _comparison(cards: list[tuple[str, str, dict]]) -> list[tuple]:
    """The table of battles, for the terminal and the page alike. Each card is (name, who commanded, data). The first
    row is the names, and every other row is a measure and one cell per battle."""
    rows = [("", *[name for name, _, _ in cards]), ("Scenario", *[d["name"] for _, _, d in cards]),
            ("Commander", *[who for _, who, _ in cards])]
    for label, show in COMPARED:
        rows.append((label, *[show(d["score"]) for _, _, d in cards]))
    rows.append(("Tokens written", *[str(d["commander"].get("output_tokens", "-")) for _, _, d in cards]))
    return rows


CSV_COLUMNS = ["battle", "scenario", "model", "seed", "hidden", "outcome", "ended", "duration_s", "friendly_lost",
               "friendly_total", "enemy_killed", "enemy_total", "first_contact_s", "turns", "orders", "questions",
               "enemy_markers", "marker_error_m", "position_error_m", "rounds_fired", "rounds_per_kill",
               "own_fire_deaths", "friendly_fire_deaths", "threat_reported_s", "silenced", "silence_noticed_s",
               "output_tokens"]


def _csv(cards: list[tuple[str, str, dict]]) -> str:
    """One row per battle, every measure, for a spreadsheet or a script. "hidden" is what the seed chose."""
    out = io.StringIO()
    writer = csv.DictWriter(out, CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for name, who, data in cards:
        writer.writerow({**data["score"], "battle": name, "scenario": data.get("scenario"), "model": who,
                         "hidden": data.get("hidden", ""), "output_tokens": data["commander"].get("output_tokens", "")})
    return out.getvalue()


COMPARED = [
    ("Outcome", lambda s: s["outcome"]),
    ("Seed", lambda s: "-" if s.get("seed") is None else s["seed"]),
    ("Result", lambda s: s["ended"]),
    ("Duration", lambda s: _clock(s["duration_s"])),
    ("Friendly lost", lambda s: f"{s['friendly_lost']} of {s['friendly_total']}"),
    ("Enemy killed", lambda s: f"{s['enemy_killed']} of {s['enemy_total']}"),
    ("First contact", lambda s: _clock(s["first_contact_s"])),
    ("Turns", lambda s: s["turns"]),
    ("Orders", lambda s: s["orders"]),
    ("Questions", lambda s: s["questions"]),
    ("Enemy markers", lambda s: s["enemy_markers"]),
    ("Marker error", lambda s: _metres(s["marker_error_m"])),
    ("Position error", lambda s: _metres(s["position_error_m"])),
    ("Rounds fired", lambda s: s["rounds_fired"]),
    ("Rounds per kill", lambda s: "-" if s.get("rounds_per_kill") is None else s["rounds_per_kill"]),
    ("Own fire deaths", lambda s: s["own_fire_deaths"]),
    ("Killed by own side", lambda s: s["friendly_fire_deaths"]),
    ("Weapon first listed", lambda s: _clock(s.get("threat_reported_s"))),
    ("Silence noticed", lambda s: "-" if not s.get("silenced") else
     f"{s['silenced']}: {'never' if s['silence_noticed_s'] is None else _clock(s['silence_noticed_s']) + ' later'}"),
]


def _clock(seconds: int | None) -> str:
    return "-" if seconds is None else f"{seconds // 60}:{seconds % 60:02d}"


def _metres(value: int | None) -> str:
    return "-" if value is None else f"{value} m"


def _battle_name(name: str) -> tuple[str, int | None]:
    run, _, attempt = name.partition(":")
    return run, int(attempt) if attempt else None


def _battle_order(folder: Path) -> tuple[str, int]:
    return folder.parent.parent.name, int(folder.parent.name.split("-")[1])


def _scenario_name(folder: Path) -> str | None:
    info = folder.parent / "battle.json"
    return json.loads(info.read_text(encoding="utf-8")).get("scenario", {}).get("name") if info.exists() else None


def _until_clock_restarts(rows: list[dict]) -> list[dict]:
    """Older records can run on into the next mission: a server left running kept writing what it saw there."""
    kept: list[dict] = []
    for row in rows:
        if row.get("t", 0) < (kept[-1]["t"] if kept else 0):
            break
        kept.append(row)
    return kept


def _outside_battle(kill: dict, truth: list[dict], wanted: set[str]) -> bool:
    """A death that wasn't one of the battle's own. In older records, it's the soldier in the observer slot when nobody
    was playing it, who shows up standing where a group outside the battle was."""
    place = kill.get("victimPos")
    before = [row for row in truth if 0 <= row.get("t", 0) <= kill.get("t", 0)]
    if not place or not before:
        return False
    return any(group.get("pos") and group.get("group") not in wanted and math.dist(group["pos"][:2], place[:2]) < 3
               for group in before[-1].get("groups") or [])


def _group(group: dict) -> dict:
    pos = group.get("pos") or []
    return {"group": group["group"], "alive": _able(group), "pos": pos,
            "units": [unit[:2] for unit in group.get("units") or ([pos] if pos else [])]}


def _radio(row: dict, world_size: float) -> dict:
    out = {key: row.get(key) for key in ("t", "from", "to", "text", "kind", "precedence")}
    if row.get("from") != "HQ":
        # Older battles didn't record it, and their reports had no grids of other things to confuse this with.
        grid = row["grid"] if "grid" in row else reported_position(row.get("text", ""))
        out["pos"] = _world(grid, world_size)
        checked = _CHECKED.match(row.get("text", ""))
        if checked:
            out["checked"] = checked[1]
    return out


def _world(grid, world_size: float) -> list[float] | None:
    try:
        return parse_grid(grid, world_size, precise=True)[0] if grid else None
    except Invalid:
        return None


def _kill(row: dict, own_side: str) -> dict:
    return {**row, "friendly": str(row.get("side", "")).lower() == own_side.lower()}


def _shell(row: dict, own_side: str) -> dict:
    ammo = str(row.get("ammo", ""))
    return {"t": row["t"], "pos": row.get("pos"), "aim": row.get("aim"), "gun": row.get("gun"),
            "order": row.get("order"), "smoke": "smoke" in ammo.lower(),
            "friendly": str(row.get("side", "")).lower() == own_side.lower()}


def _mission(row: dict, shells: list[dict]) -> dict:
    landed = [shell["t"] for shell in shells if shell["order"] == row["id"]]
    return {"t": row["t"], "id": row["id"], "by": row.get("by"), "aim": row["aim"], "grid": row.get("grid"),
            "ammo": row.get("ammo"), "rounds": row.get("rounds"), "observer": row.get("observer"),
            "until": max(landed, default=row["t"] + 60) + 15}


def _judge_kill(kill: dict, shells: list[dict], missions: list[dict], frames: list[dict], radio: list[dict],
                stations: set[str], world_size: float) -> None:
    """What killed this man, if it was a shell, and for a friendly killed by a friendly gun, whether the commander was
    misled by the fog, chose it, or the harness let it down."""
    place = (kill.get("victimPos") or [])[:2]
    if not place:
        return
    close = [shell for shell in shells if not shell["smoke"] and shell.get("pos")
             and 0 <= kill["t"] - shell["t"] <= SHELL_KILL_S and math.dist(shell["pos"], place) <= SHELL_KILL_M]
    if not close:
        return
    shell = min(close, key=lambda s: math.dist(s["pos"], place))
    kill["shell"] = {"gun": shell["gun"], "order": shell["order"]}
    if kill["friendly"] and shell["friendly"]:
        mission = next((row for row in missions if row["id"] == shell["order"]), None)
        kill["verdict"] = _verdict(kill, shell, mission, frames, radio, stations, world_size)


def _verdict(kill, shell, mission, frames, radio, stations, world_size) -> dict:
    if mission is None:
        return {"kind": "bug", "why": f"{shell['gun']} fired with no order. Its crew should never fire by itself."}
    aim, fired = mission["aim"], mission["t"]
    station = _station_at(kill["victimPos"][:2], _frame_at(frames, kill["t"]), stations)
    if station is None:
        return {"kind": "fog", "why": "He wasn't in a station the record can place."}
    report = (mission.get("positions") or {}).get(station)
    really = _where(station, _frame_at(frames, fired))
    away = f"really {round(math.dist(really, aim))} m from the aim" if really else "somewhere the record doesn't show"
    if report is None:
        return {"kind": "fog", "why": f"{station} hadn't reported a position when this was fired. It was {away}."}
    reported = _world(report["grid"], world_size)
    said = next((row for row in reversed(radio) if row["t"] <= fired and row.get("from") == station and row.get("pos")),
                None)
    if said and reported and math.dist(said["pos"], reported) > MOVED_M:
        return {"kind": "bug", "why": f"{station}'s last report on the radio wasn't the place the commander was given."}
    age, gap = round(fired - report["t"]), round(math.dist(reported, aim))
    if gap <= DANGER_CLOSE_M:
        return {"kind": "decision", "why": f"{station}'s last report, {age} s before firing, was {gap} m from the aim."}
    if really and math.dist(really, reported) > MOVED_M:
        return {"kind": "fog", "why": f"{station}'s last report, {age} s before firing, was {gap} m from the aim. "
                                      f"It had moved, and was {away}."}
    miss = round(math.dist(shell["pos"], aim))
    return {"kind": "fog", "why": f"{station} was where it said, {gap} m from the aim. This round fell {miss} m from "
                                  "the aim, or it moved after the order."}


def _frame_at(frames: list[dict], t: float) -> dict | None:
    return next((frame for frame in reversed(frames) if frame["t"] <= t), frames[0] if frames else None)


def _where(station: str, frame: dict | None) -> list[float] | None:
    for group in (frame or {}).get("groups", []):
        if group["group"] == station and group["pos"]:
            return group["pos"][:2]
    return None


def _station_at(place: list[float], frame: dict | None, stations: set[str]) -> str | None:
    best, nearest = None, math.inf
    for group in (frame or {}).get("groups", []):
        if group["group"] in stations:
            for unit in group["units"]:
                metres = math.dist(unit[:2], place)
                if metres < nearest:
                    best, nearest = group["group"], metres
    return best


def _markers(records: Records, scenario: dict, world_size: float) -> list[dict]:
    """The marker history, starting from those the commander was given. Positions are worked out from its grids."""
    given = [{"id": m["id"], "kind": m.get("kind", "note"), "at": m["at"], "label": m.get("label", ""), "t": 0}
             for m in scenario.get("markers") or []]
    rows = sorted(given + records.read("markers"), key=lambda row: row.get("t", 0))
    for row in rows:
        at = row.get("at")
        if isinstance(at, list):
            row["points"] = [point for point in (_world(grid, world_size) for grid in at) if point]
        elif at:
            row["pos"] = row.get("pos") or _world(at, world_size)
    return rows


def _order(row: dict, buildings: list[dict], markers: list[dict], world_size: float) -> dict:
    request = row.get("request") or {}
    legs = request.get("legs") or [{}]
    last = legs[-1]
    return {"t": row["t"], "id": row.get("id"), "to": request.get("to"), "type": last.get("type"),
            "intent": request.get("intent", ""), "target": _target(last.get("at"), buildings, markers, world_size)}


def _target(at, buildings: list[dict], markers: list[dict], world_size: float) -> list[float] | None:
    """Where an order points. Orders that pick out a place by building or marker id resolve to that place."""
    if isinstance(at, list):
        at = at[-1] if at else None
    if not isinstance(at, str):
        return None
    name = at.strip()
    for building in buildings:
        if building["id"] == name:
            return building["pos"]
    for marker in reversed(markers):
        if marker.get("id") == name:
            return marker.get("pos")
    return _world(name, world_size)


def _turns(records: Records, state: dict, commander: dict | None) -> list[dict]:
    turns = list(records.read("turns"))
    open_turn = state.get("turn_row")
    if open_turn and not any(row.get("turn") == open_turn.get("turn") for row in turns):
        turns.append(open_turn)
    said = (commander or {}).get("turns") or {}
    return [{**row, **said.get(row.get("turn"), {})} for row in turns]


# -- what the commander itself did, from its client's session transcript -----------------------------------------------

def commander_session(folder: Path, projects: Path | None = None) -> dict | None:
    """The session that fought this battle: its model, its token use, and per turn what it said and did. None if no
    session did, which means a scripted test or a transcript that's gone. Reads only the commander's own words and
    tool calls, so nothing else in the transcript reaches the page."""
    window = _battle_window(folder)
    if window is None:
        return None
    client = folder / "client.json"
    if client.exists():
        info = json.loads(client.read_text(encoding="utf-8"))
        if info.get("client") == "opencode":
            return opencode_session(folder, info)
    if projects is None:
        workspace = Home().root / "commander" / "workspace"
        projects = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(workspace))
    starts = [(row["start"], row["turn"]) for row in Records(folder).read("turns") if "start" in row and "turn" in row]
    best, best_calls = None, 0
    for file in sorted(projects.glob("*.jsonl")) if projects.exists() else []:
        session = _read_session(file, window, starts)
        if session and session["tool_calls"] > best_calls:
            best, best_calls = session, session["tool_calls"]
    return best


def _battle_window(folder: Path) -> tuple[float, float] | None:
    info, state = folder.parent / "battle.json", folder / "state.json"
    if not info.exists() or not state.exists():
        return None
    return info.stat().st_mtime, state.stat().st_mtime + 5


def _read_session(file: Path, window: tuple[float, float], starts: list[tuple[float, int]]) -> dict | None:
    """Everything it said and did gets a battle time, counted from its first look at the mission, which is what starts
    the battle clock. A wake that arrives while the model is busy leaves no user row in the transcript, so time places
    what follows in the right turn."""
    turns: dict[int, dict] = {}
    begun: float | None = None
    model, requests, output_tokens, peak_context, tool_calls = None, set(), 0, 0, 0
    other_calls: Counter[str] = Counter()
    turn, typed_before, answering_person = 1, False, False
    rows = [row for row in map(_json, file.read_text(encoding="utf-8").splitlines()) if row]
    for row in rows:
        if not _in_window(row.get("timestamp"), window):
            continue
        kind = row.get("type")
        if kind == "attachment" and (row.get("attachment") or {}).get("type") == "model":
            model = row["attachment"].get("identity", {}).get("marketingName") or model
        elif kind == "user":
            content = (row.get("message") or {}).get("content")
            if isinstance(content, str):
                woke = re.match(r'<channel source="commander" turn="(\d+)"', content)
                if woke:
                    turn, answering_person = int(woke[1]), False
                elif not content.startswith("<") and not row.get("isMeta") and not row.get("isCompactSummary"):
                    # Whoever launched it typed something. The first time, that's "start". Replies to anything later
                    # are a chat with a person rather than part of the battle.
                    answering_person, typed_before = typed_before, True
        elif kind == "assistant" and not answering_person:
            message = row.get("message") or {}
            model = model or message.get("model")
            usage = message.get("usage") or {}
            if message.get("id") not in requests:
                requests.add(message.get("id"))
                output_tokens += usage.get("output_tokens", 0)
                peak_context = max(peak_context, sum(usage.get(key, 0) for key in (
                    "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")))
            moment = _moment(row.get("timestamp"))
            blocks = message.get("content") or []
            if begun is None and any(block.get("name") == f"{_TOOL}mission" for block in blocks):
                begun = moment
            at = 0.0 if begun is None or moment is None else round(max(0.0, moment - begun), 1)
            turn = max([turn, *(number for start, number in starts if begun is not None and start <= at)])
            entry = turns.setdefault(turn, {"said": [], "actions": []})
            for block in blocks:
                if block.get("type") == "text" and block.get("text", "").strip():
                    entry["said"].append({"t": at, "text": block["text"].strip()})
                elif block.get("type") == "tool_use" and block.get("name", "").startswith(_TOOL):
                    tool_calls += 1
                    tool = block["name"][len(_TOOL):]
                    if tool in _ACTIONS:
                        entry["actions"].append({"t": at, "tool": tool, "input": block.get("input") or {}})
                elif block.get("type") == "tool_use":
                    other_calls[block.get("name", "")] += 1
    if not tool_calls:
        return None
    # What this session was really offered. A one-shot lockdown check can see fewer tools than this one did.
    outside = judge_lockdown(tools_received(rows)).get("unexpected", [])
    return {"model": model, "requests": len(requests), "output_tokens": output_tokens, "peak_context": peak_context,
            "tool_calls": tool_calls, "turns": turns, "tools_outside_lockdown": outside,
            "outside_lockdown_used": {name: other_calls[name] for name in outside if other_calls[name]}}


OPENCODE_EXPORT = "opencode_session.json"
_OPENCODE_TOOL = "commander_commander_"


def opencode_session(folder: Path, info: dict, service=None) -> dict | None:
    """The same as commander_session, for a battle fought in OpenCode, from its session as OpenCode exports it.

    The export is kept beside the battle's records, so a review still works once OpenCode has deleted the session,
    and is fetched afresh whenever OpenCode can be reached, in case the battle was reviewed before it was over."""
    from . import opencode

    saved = folder / OPENCODE_EXPORT
    try:
        service = service or opencode.Service(opencode.find_cli() or "opencode")
        export = service.call("GET", f"/api/experimental/session/{info['session']}/export")["data"]
        saved.write_text(json.dumps(export), encoding="utf-8")
    except Exception:
        if not saved.exists():
            return None
        export = json.loads(saved.read_text(encoding="utf-8"))
    starts = [(row["start"], row["turn"]) for row in Records(folder).read("turns") if "start" in row and "turn" in row]
    session = _read_opencode(export.get("messages") or [], starts)
    if session is not None:
        lockdown = info.get("lockdown") or {}
        session["tools_outside_lockdown"] = lockdown.get("allowed_outside", [])
        if not lockdown.get("ok", False) and not session["tools_outside_lockdown"]:
            session["tools_outside_lockdown"] = ["(the lockdown couldn't be checked)"]
    return session


def _read_opencode(messages: list[dict], starts: list[tuple[float, int]]) -> dict | None:
    """As _read_session, from OpenCode's messages: oldest first, with every wake a user message of its own."""
    turns: dict[int, dict] = {}
    begun: float | None = None
    model, requests, output_tokens, reasoning_tokens, peak_context, tool_calls = None, 0, 0, 0, 0, 0
    other_calls: Counter[str] = Counter()
    turn, typed_before, answering_person = 1, False, False
    for message in messages:
        kind = message.get("type")
        if kind == "user":
            woke = re.match(r'<channel source="commander" turn="(\d+)"', message.get("text") or "")
            if woke:
                turn, answering_person = int(woke[1]), False
            else:  # as with Claude Code: "start" first, and a chat with a person after that
                answering_person, typed_before = typed_before, True
        elif kind == "assistant" and not answering_person:
            model = model or (message.get("model") or {}).get("id")
            tokens = message.get("tokens") or {}
            cache = tokens.get("cache") or {}
            requests += 1
            output_tokens += tokens.get("output", 0)
            reasoning_tokens += tokens.get("reasoning", 0)
            peak_context = max(peak_context, tokens.get("input", 0) + cache.get("read", 0) + cache.get("write", 0))
            moment = ((message.get("time") or {}).get("created") or 0) / 1000 or None
            parts = message.get("content") or []
            if begun is None and any(part.get("name") == f"{_OPENCODE_TOOL}mission" for part in parts):
                begun = moment
            at = 0.0 if begun is None or moment is None else round(max(0.0, moment - begun), 1)
            turn = max([turn, *(number for start, number in starts if begun is not None and start <= at)])
            entry = turns.setdefault(turn, {"said": [], "actions": []})
            for part in parts:
                if part.get("type") == "text" and (part.get("text") or "").strip():
                    entry["said"].append({"t": at, "text": part["text"].strip()})
                elif part.get("type") == "tool" and part.get("name", "").startswith(_OPENCODE_TOOL):
                    tool_calls += 1
                    tool = part["name"][len(_OPENCODE_TOOL):]
                    if tool in _ACTIONS:
                        given = (part.get("state") or {}).get("input") or {}
                        entry["actions"].append({"t": at, "tool": tool, "input": given})
                elif part.get("type") == "tool":
                    other_calls[part.get("name", "")] += 1
    if not tool_calls:
        return None
    return {"model": model, "requests": requests, "output_tokens": output_tokens, "reasoning_tokens": reasoning_tokens,
            "peak_context": peak_context, "tool_calls": tool_calls, "turns": turns, "client": "opencode",
            "tools_outside_lockdown": [], "outside_lockdown_used": dict(other_calls)}


def _json(line: str) -> dict | None:
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


def _moment(stamp) -> float | None:
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp() if stamp else None
    except ValueError:
        return None


def _in_window(stamp, window: tuple[float, float]) -> bool:
    moment = _moment(stamp)
    return moment is not None and window[0] <= moment <= window[1]


# -- the page ----------------------------------------------------------------------------------------------------------

def render(data: dict) -> str:
    page = resources.files("arma_harness.commander").joinpath("aar_viewer.html").read_text(encoding="utf-8")
    # "</" inside the data would otherwise close the script element it's embedded in.
    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return page.replace(DATA_SLOT, embedded)


def find_battle(home: Home, run: str | None = None, attempt: int | None = None) -> Path:
    """A battle's records folder: the given run and attempt, or else the newest."""
    if run and not (home.runs / run).is_dir():
        raise ValueError(f"no run called {run}")
    folders = [path.parent for path in (home.runs / run if run else home.runs).glob(
        f"{'' if run else '*/'}commander-{attempt or '*'}/*/radio.jsonl")]
    if not folders:
        raise ValueError("no commander battle found" + (f" in run {run}" if run else ""))
    return max(folders, key=_battle_order)


def write(folder: Path, out: Path | None = None, projects: Path | None = None) -> dict:
    data = battle_data(folder, commander_session(folder, projects))
    out = out or folder.parent / "review.html"
    out.write_text(render(data), encoding="utf-8")
    return {"review": str(out), "battle": data["name"], "run": data["run"], "attempt": data["attempt"],
            "ended": data["ended"], "commander": data["commander"].get("model") or "no model session found",
            "tools_outside_lockdown": data["commander"].get("tools_outside_lockdown", [])}


def site(home: Home, battles: list[str], out: Path, projects: Path | None = None, note: str = "") -> dict:
    """Several battles in one page, with a picker and a comparison, to publish or send. Each is RUN[:ATTEMPT][=Label],
    or a records folder in place of the run. The page opens on the first, and compares those that share its mission."""
    if not battles:
        raise ValueError("commander site needs at least one --battle RUN[:ATTEMPT][=Label]")
    picked = []
    for spec in battles:
        source, _, label = spec.partition("=")
        folder = Path(source) if Path(source).is_dir() else find_battle(home, *_battle_name(source))
        data = battle_data(folder, commander_session(folder, projects))
        model = data["commander"].get("model")
        run_id = re.sub(r"[^A-Za-z0-9-]", "-", f"{data['run']}-{data['attempt'] or _battle_order(folder)[1]}")
        picked.append({**data, "id": run_id, "label": label or model or "Script"})
    alike = [data for data in picked if data["name"] == picked[0]["name"]]
    cards = [(data["label"], data["commander"].get("model") or "Script, no AI", data) for data in alike]
    compared = {"ids": [data["id"] for data in alike], "rows": _comparison(cards), "note": note}
    page = {"battles": picked, "compare": compared}
    out.write_text(render(page), encoding="utf-8")
    return {"site": str(out), "bytes": out.stat().st_size, "opens_on": picked[0]["label"],
            "battles": [{"id": data["id"], "label": data["label"], "ended": data["ended"],
                         "commander": data["commander"].get("model") or "no model session found",
                         "compared": data in alike} for data in picked]}
