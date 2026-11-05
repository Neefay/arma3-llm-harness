"""After-action review: one self-contained HTML page replaying a battle from its records, belief against truth.

For people only. The commander has no tool that reaches any of this. The page holds everything it needs, so it can be
opened long after the run's other files are gone. Its map of what the commander believed is built only from words the
commander received, by reading the same radio text it read.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from importlib import resources
from pathlib import Path

from ..config import Home
from .orders import Invalid, parse_grid
from .records import Records
from .runtime import RECORD_AFTER_END_S

DATA_SLOT = "/*BATTLE_DATA*/"
_POSITION = re.compile(r"(?:^|\bat |, )grid (\d{3} \d{3})", re.IGNORECASE)
_CHECKED = re.compile(r"^(B\d+) checked\b")
_TOOL = "mcp__commander__commander_"
_ACTIONS = {"order", "ask", "schedule", "unschedule", "mark", "unmark", "notes"}


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

    ended_at = next((row["t"] for row in records.read("radio_events") if "mission_end" in row), None)
    cutoff = None if ended_at is None else ended_at + RECORD_AFTER_END_S

    def in_battle(row: dict) -> bool:
        return cutoff is None or row.get("t", 0) <= cutoff

    frames = [{"t": row["t"], "groups": [_group(g) for g in row.get("groups") or [] if g.get("group") in wanted]}
              for row in _until_clock_restarts(records.read_truth()) if in_battle(row)]
    radio = [_radio(row, world_size) for row in records.read("radio") if in_battle(row)]
    markers = _markers(records, scenario, world_size)
    kills = [_kill(row, folder.name) for row in _until_clock_restarts(records.read_kills()) if in_battle(row)]
    turns = _turns(records, state, commander)
    orders = [_order(row, info.get("buildings") or [], markers, world_size) for row in records.read("orders")]
    latest = [row["t"] for rows in (frames, radio, kills) for row in rows[-1:]] + [t["start"] for t in turns[-1:]]
    data = {
        "name": str(scenario.get("name", folder.parent.name)).replace("_", " ").capitalize(),
        "text": str(scenario.get("text", "")).strip(),
        "run": info.get("run", folder.parent.parent.name), "attempt": info.get("attempt"),
        "mode": scenario.get("mid_turn_messages"), "ended": state.get("ended") or None, "ended_at": ended_at,
        "commander": {key: value for key, value in (commander or {}).items() if key != "turns"},
        "duration": max(latest, default=1), "world_size": world_size,
        "buildings": info.get("buildings") or [], "stations": stations, "enemies": enemy_ids,
        "enemy_total": sum(enemy.get("units", 4) for enemy in enemies), "frames": frames, "kills": kills,
        "radio": radio, "turns": turns, "markers": markers, "orders": orders, "notes": records.notes(),
    }
    return {**data, "score": scorecard(data)}


def scorecard(data: dict) -> dict:
    """The measures for comparing battles. The last two say how wrong the commander's picture of the battle was."""
    frames = data["frames"]
    left = {group["group"]: group["alive"] for group in frames[-1]["groups"]} if frames else {}
    friendly_total = sum(station["units"] for station in data["stations"].values())
    return {
        "ended": data["ended"] or "Didn't finish", "duration_s": round(data["duration"]),
        "friendly_lost": friendly_total - sum(left.get(name, 0) for name in data["stations"]),
        "friendly_total": friendly_total,
        "enemy_killed": data["enemy_total"] - sum(left.get(name, 0) for name in data["enemies"]),
        "enemy_total": data["enemy_total"],
        "first_contact_s": next((round(row["t"]) for row in data["radio"]
                                 if row.get("from") != "HQ" and str(row.get("text")).startswith("Contact")), None),
        "turns": len(data["turns"]), "orders": len(data["orders"]),
        "questions": sum(row.get("kind") == "question" for row in data["radio"]),
        "enemy_markers": len({row["id"] for row in data["markers"] if row.get("kind") == "enemy"}),
        "marker_error_m": _marker_error(data), "position_error_m": _position_error(data),
    }


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
                   if group["group"] in heard and group["alive"] and group["pos"]]
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


def compare(home: Home, battles: list[str] | None = None) -> str:
    """Battles side by side, as a table. Each is RUN or RUN:ATTEMPT. By default, every battle of the newest one's
    scenario that ran long enough to mean something."""
    if battles:
        folders = [find_battle(home, *_battle_name(name)) for name in battles]
    else:
        newest = _scenario_name(find_battle(home))
        folders = sorted((path.parent for path in home.runs.glob("*/commander-*/*/radio.jsonl")
                          if _scenario_name(path.parent) == newest), key=_battle_order)
    cards = []
    for folder in folders:
        data = battle_data(folder, commander_session(folder))
        if battles or data["ended"]:
            run, attempt = _battle_order(folder)
            cards.append((f"{run}:{attempt}", data["commander"].get("model") or "Scripted", data))
    if not cards:
        raise ValueError("no finished battle to compare")
    rows = [("", *[name for name, _, _ in cards]), ("Scenario", *[d["name"] for _, _, d in cards]),
            ("Commander", *[who for _, who, _ in cards])]
    for label, show in COMPARED:
        rows.append((label, *[show(d["score"]) for _, _, d in cards]))
    rows.append(("Tokens written", *[str(d["commander"].get("output_tokens", "-")) for _, _, d in cards]))
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
    return "\n".join("  ".join(str(cell).ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
                     for row in rows)


COMPARED = [
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


def _group(group: dict) -> dict:
    pos = group.get("pos") or []
    return {"group": group["group"], "alive": group.get("alive", 0), "pos": pos,
            "units": [unit[:2] for unit in group.get("units") or ([pos] if pos else [])]}


def _radio(row: dict, world_size: float) -> dict:
    out = {key: row.get(key) for key in ("t", "from", "to", "text", "kind", "precedence")}
    if row.get("from") != "HQ":
        grid = reported_position(row.get("text", ""))
        out["pos"] = _world(grid, world_size)
        checked = _CHECKED.match(row.get("text", ""))
        if checked:
            out["checked"] = checked[1]
    return out


def _world(grid, world_size: float) -> list[float] | None:
    try:
        return parse_grid(grid, world_size)[0] if grid else None
    except Invalid:
        return None


def _kill(row: dict, own_side: str) -> dict:
    return {**row, "friendly": str(row.get("side", "")).lower() == own_side.lower()}


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
    if projects is None:
        workspace = Home().root / "commander" / "workspace"
        projects = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(workspace))
    best, best_calls = None, 0
    for file in sorted(projects.glob("*.jsonl")) if projects.exists() else []:
        session = _read_session(file, window)
        if session and session["tool_calls"] > best_calls:
            best, best_calls = session, session["tool_calls"]
    return best


def _battle_window(folder: Path) -> tuple[float, float] | None:
    info, state = folder.parent / "battle.json", folder / "state.json"
    if not info.exists() or not state.exists():
        return None
    return info.stat().st_mtime, state.stat().st_mtime + 5


def _read_session(file: Path, window: tuple[float, float]) -> dict | None:
    turns: dict[int, dict] = {}
    model, requests, output_tokens, peak_context, tool_calls = None, set(), 0, 0, 0
    turn, typed_before, answering_person = 1, False, False
    for line in file.read_text(encoding="utf-8").splitlines():
        row = _json(line)
        if not row or not _in_window(row.get("timestamp"), window):
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
            entry = turns.setdefault(turn, {"said": [], "actions": []})
            for block in message.get("content") or []:
                if block.get("type") == "text" and block.get("text", "").strip():
                    entry["said"].append(block["text"].strip())
                elif block.get("type") == "tool_use" and block.get("name", "").startswith(_TOOL):
                    tool_calls += 1
                    tool = block["name"][len(_TOOL):]
                    if tool in _ACTIONS:
                        entry["actions"].append({"tool": tool, "input": block.get("input") or {}})
    if not tool_calls:
        return None
    return {"model": model, "requests": len(requests), "output_tokens": output_tokens, "peak_context": peak_context,
            "tool_calls": tool_calls, "turns": turns}


def _json(line: str) -> dict | None:
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


def _in_window(stamp, window: tuple[float, float]) -> bool:
    if not stamp:
        return False
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return False
    return window[0] <= moment <= window[1]


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
            "ended": data["ended"], "commander": data["commander"].get("model") or "no model session found"}
