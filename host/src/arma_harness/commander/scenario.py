"""Commander scenario files: who is on the net, the mission, when it ends. In scenarios/commander/."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import REPO_ROOT
from .orders import ORDER_TYPES, parse_time
from .wake import DELIVER, HOLD

SCENARIO_DIR = REPO_ROOT / "scenarios" / "commander"


@dataclass
class Scenario:
    name: str
    mission: str
    text: str
    time_limit_s: float
    stations: dict[str, dict]
    side: str = "west"
    markers: dict[str, dict] = field(default_factory=dict)
    success: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    quiet_s: float = 3.0
    ceiling_s: float = 15.0
    mid_turn_messages: str = HOLD


def load(path: str | Path) -> Scenario:
    """Load by path, or by name from scenarios/commander/."""
    file = Path(path)
    if not file.exists():
        file = SCENARIO_DIR / f"{path}.yaml"
    raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    return build(raw)


def build(raw: dict) -> Scenario:
    stations = {}
    for station in raw["stations"]:
        unknown = set(station.get("capabilities", [])) - ORDER_TYPES
        if unknown:
            raise ValueError(f"{station['callsign']}: unknown capabilities {sorted(unknown)}")
        stations[station["callsign"]] = {
            "callsign": station["callsign"], "role": station["role"], "capabilities": station["capabilities"],
            "at": station["at"], "units": station.get("units", 4), "class": station.get("class", "B_Soldier_F"),
        }
    debounce = raw.get("debounce") or {}
    mode = raw.get("mid_turn_messages", HOLD)
    if mode not in (HOLD, DELIVER):
        raise ValueError(f"mid_turn_messages must be {HOLD} or {DELIVER}, not {mode!r}")
    events = [{**event, "at_s": parse_time(event["at"])} for event in raw.get("events") or []]
    for event in events:
        if event.get("action") not in ("delete_station", "kill_station") or event.get("station") not in stations:
            raise ValueError(f"bad scenario event: {event}")
    return Scenario(
        name=raw["name"], mission=raw["mission"], text=raw["text"].strip(),
        time_limit_s=parse_time(raw["time_limit"]), stations=stations, side=raw.get("side", "west"),
        markers={m["id"]: m for m in raw.get("markers") or []}, success=raw.get("success") or {}, events=events,
        quiet_s=debounce.get("quiet_s", 3.0), ceiling_s=debounce.get("ceiling_s", 15.0), mid_turn_messages=mode,
    )
