"""Commander scenario files: who is on the net, the mission, when it ends. In scenarios/commander/."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import REPO_ROOT
from .orders import ORDER_TYPES, parse_grid, parse_time
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
    failure: dict = field(default_factory=dict)
    enemies: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    spectator: bool = False
    ao: dict = field(default_factory=dict)  # {at, radius}: the area whose buildings the commander is told about
    vehicles: list[dict] = field(default_factory=list)  # guns and vehicles placed in the world
    quiet_s: float = 3.0
    ceiling_s: float = 15.0
    mid_turn_messages: str = HOLD
    objectives: list[dict] = field(default_factory=list)  # {id, text, success}. The battle's won when all are done
    medical: dict = field(default_factory=dict)  # field_s, facility_s and build_s, over the game's defaults


def load(path: str | Path) -> Scenario:
    """Load by path, or by name from scenarios/commander/."""
    file = Path(path)
    if not file.exists():
        file = SCENARIO_DIR / f"{path}.yaml"
    raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    return build(raw)


FAILURE_KEYS = {"all_stations_lost", "casualties_pct", "critical"}


def _failure(failure: dict, stations: dict, vehicles: list[dict]) -> dict:
    """How the battle can be lost, besides running out of time: all stations lost, casualties over a share of the
    starting strength, or a critical station (all its men dead) or vehicle (destroyed) lost."""
    unknown = set(failure) - FAILURE_KEYS
    if unknown:
        raise ValueError(f"unknown failure conditions {sorted(unknown)}: use {sorted(FAILURE_KEYS)}")
    pct = failure.get("casualties_pct")
    if pct is not None and not (isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 < pct <= 100):
        raise ValueError(f"casualties_pct must be a percentage above 0, up to 100: {pct!r}")
    critical = failure.get("critical") or []
    known = set(stations) | {vehicle["id"] for vehicle in vehicles}
    if not isinstance(critical, list) or set(critical) - known:
        raise ValueError(f"critical must list stations or vehicles of this scenario: {critical!r}")
    return failure


def failure_words(failure: dict, stations: dict, vehicles: list[dict]) -> list[str]:
    """The failure conditions as the briefing states them. Made from the same settings the harness checks."""
    words = []
    if failure.get("casualties_pct"):
        start = sum(station.get("units", 1) for station in stations.values())
        words.append(f"{failure['casualties_pct']:g}% or more of your men are dead or down at the same time, out of "
                     f"the {start} you start with.")
    for item in failure.get("critical") or []:
        if item in stations:
            words.append(f"{item} is lost: every one of its men dead.")
        else:
            words.append(f"{item} is destroyed.")
    if failure.get("all_stations_lost"):
        words.append("Every station is lost.")
    return words


def _objectives(raw: dict) -> list[dict]:
    """A list under `objectives`, or the one a simple scenario describes with `objective` and `success`."""
    if raw.get("objectives") and (raw.get("success") or raw.get("objective")):
        raise ValueError("use either objectives, or objective and success, not both")
    listed = raw.get("objectives") or [{"id": "OBJ1", "text": raw.get("objective") or raw["text"],
                                        "success": raw.get("success") or {}}]
    out = []
    for item in listed:
        if not item.get("id") or not item.get("text"):
            raise ValueError(f"an objective needs an id and text: {item}")
        success = item.get("success") or {}
        if success and not {"enemy_cleared", "stations", "station", "men"} & set(success):
            raise ValueError(f"{item['id']}: unknown success {success}")
        if ({"stations", "station", "men"} & set(success)) and not {"of", "within_m"} <= set(success):
            raise ValueError(f"{item['id']}: a station's success needs of and within_m: {success}")
        out.append({"id": item["id"], "text": str(item["text"]).strip(), "success": success})
    ids = [item["id"] for item in out]
    if len(set(ids)) != len(ids):
        raise ValueError(f"objective ids must be unique: {ids}")
    return out


def draw(raw: dict, seed: int | None = None) -> tuple[dict, int, list[list]]:
    """Resolves the scenario's random draws, so each battle can differ while staying one battle once it starts. Any
    value may instead be:

        {one_of: [a, b, c]}                  one of these, which may be grids, times or whole entries
        {between: [lo, hi]}                  a whole number, or a time such as "8:00", in that range
        {around: "032 029", within_m: 300}   a grid somewhere within that distance of a place

    Things that have to be drawn together, such as which post goes silent and where the enemy comes through, go under
    `variant: {one_of: [...]}`: the one drawn is a bundle of entries, added to the scenario's own lists.

    Returns the resolved scenario, the seed, and what was drawn as [where, value] rows for the record."""
    seed = random.randrange(1 << 31) if seed is None else seed
    rng, drawn = random.Random(seed), []
    resolved = _draw(raw, rng, "", drawn)
    variant = resolved.pop("variant", None)
    if variant is not None:
        if not isinstance(variant, dict):
            raise ValueError("variant must be a bundle of entries, such as {enemies: [...], events: [...]}")
        for key, value in variant.items():
            resolved[key] = (resolved.get(key) or []) + value if isinstance(value, list) else value
    return resolved, seed, drawn


def _draw(node, rng: random.Random, where: str, drawn: list):
    if isinstance(node, list):
        return [_draw(item, rng, f"{where}[{index}]", drawn) for index, item in enumerate(node)]
    if not isinstance(node, dict):
        return node
    if set(node) == {"one_of"}:
        options = node["one_of"]
        if not isinstance(options, list) or not options:
            raise ValueError(f"{where}: one_of needs a list to choose from")
        value = _draw(rng.choice(options), rng, where, drawn)
    elif set(node) == {"between"}:
        value = _between(node["between"], rng, where)
    elif set(node) == {"around", "within_m"}:
        (x, y), _ = parse_grid(node["around"], 0)
        distance, bearing = node["within_m"] * math.sqrt(rng.random()), rng.uniform(0, 2 * math.pi)
        x, y = x + distance * math.sin(bearing), y + distance * math.cos(bearing)
        value = f"{int(x // 100):03d} {int(y // 100):03d}"
    else:
        return {key: _draw(value, rng, f"{where}.{key}" if where else key, drawn) for key, value in node.items()}
    drawn.append([where, value])
    return value


def _between(bounds, rng: random.Random, where: str):
    if not (isinstance(bounds, list) and len(bounds) == 2):
        raise ValueError(f"{where}: between needs [lowest, highest]")
    low, high = bounds
    if isinstance(low, str) and isinstance(high, str):  # times
        seconds = rng.randint(parse_time(low), parse_time(high))
        return f"{seconds // 60}:{seconds % 60:02d}"
    if isinstance(low, int) and isinstance(high, int):
        return rng.randint(low, high)
    return round(rng.uniform(float(low), float(high)), 1)


def build(raw: dict) -> Scenario:
    # Draws left in it are resolved here, for anything that only needs its shape: a battle resolves them once, on start.
    raw, _, _ = draw(raw)
    stations = {}
    for station in raw["stations"]:
        unknown = set(station.get("capabilities", [])) - ORDER_TYPES
        if unknown:
            raise ValueError(f"{station['callsign']}: unknown capabilities {sorted(unknown)}")
        stations[station["callsign"]] = {
            "callsign": station["callsign"], "role": station["role"], "capabilities": station["capabilities"],
            "at": station["at"], "units": station.get("units", 4), "class": station.get("class", "B_Soldier_F"),
            "spotter": bool(station.get("spotter")), "crew": station.get("crew") or {},
            "medics": int(station.get("medics") or 0),
        }
    debounce = raw.get("debounce") or {}
    mode = raw.get("mid_turn_messages", HOLD)
    if mode not in (HOLD, DELIVER):
        raise ValueError(f"mid_turn_messages must be {HOLD} or {DELIVER}, not {mode!r}")
    events = [{**event, "at_s": parse_time(event["at"])} for event in raw.get("events") or []]
    for event in events:
        if event.get("action") not in ("delete_station", "kill_station", "knock_down") \
                or event.get("station") not in stations:
            raise ValueError(f"bad scenario event: {event}")
    enemies = []
    for enemy in raw.get("enemies") or []:
        if enemy.get("mode", "hold") not in ("hold", "garrison", "patrol"):
            raise ValueError(f"{enemy['id']}: mode must be hold, garrison or patrol")
        if enemy.get("vehicle") and enemy.get("mode", "hold") == "garrison":
            raise ValueError(f"{enemy['id']}: a vehicle can hold or patrol, not garrison")
        enemies.append({"id": enemy["id"], "side": enemy.get("side", "east"), "at": enemy["at"],
                        "units": enemy.get("units", 4), "class": enemy.get("class", "O_Soldier_F"),
                        "mode": enemy.get("mode", "hold"), "radius": enemy.get("radius", 100),
                        "vehicle": enemy.get("vehicle") or "", "dir": float(enemy.get("dir") or 0)})
    vehicles = [{"id": vehicle["id"], "class": vehicle["class"], "at": vehicle["at"],
                 "known": vehicle.get("known", True), "ammo": vehicle.get("ammo") or {},
                 "medical": bool(vehicle.get("medical")), "fly": float(vehicle.get("fly") or 0)}
                for vehicle in raw.get("vehicles") or []]
    ids = {vehicle["id"] for vehicle in vehicles}
    for station in stations.values():
        unknown = set(station["crew"]) - ids
        if unknown:
            raise ValueError(f"{station['callsign']}: crew for unknown vehicles {sorted(unknown)}")
    return Scenario(
        objectives=_objectives(raw),
        medical=raw.get("medical") or {},
        vehicles=vehicles,
        name=raw["name"], mission=raw["mission"], text=raw["text"].strip(),
        time_limit_s=parse_time(raw["time_limit"]), stations=stations, side=raw.get("side", "west"),
        markers={m["id"]: m for m in raw.get("markers") or []}, events=events,
        failure=_failure(raw.get("failure") or {}, stations, vehicles), enemies=enemies,
        spectator=bool(raw.get("spectator")),
        ao=raw.get("ao") or {},
        quiet_s=debounce.get("quiet_s", 3.0), ceiling_s=debounce.get("ceiling_s", 15.0), mid_turn_messages=mode,
    )
