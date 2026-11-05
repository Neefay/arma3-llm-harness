"""Validating orders and scheduled times. Rejections state only what the roster and map already show."""
from __future__ import annotations

import re

_GRID = re.compile(r"^\s*(\d{3})\s?(\d{3})\s*$")
_TIME = re.compile(r"^(?:T\+)?(\d+):([0-5]\d)$")

SPEEDS = {"LIMITED", "NORMAL", "FULL"}
FORMATIONS = {"COLUMN", "STAG COLUMN", "WEDGE", "ECH LEFT", "ECH RIGHT", "VEE", "LINE", "FILE", "DIAMOND"}
BEHAVIOURS = {"CARELESS", "SAFE", "AWARE", "COMBAT", "STEALTH"}
COMBAT_MODES = {"BLUE", "GREEN", "WHITE", "YELLOW", "RED"}
LEG_TYPES = {"MOVE": "MOVE", "HOLD": "HOLD", "SEARCH": "SAD", "SENTRY": "SENTRY"}
ORDER_TYPES = set(LEG_TYPES) | {"PATROL", "HALT", "POSTURE"}


class Invalid(ValueError):
    """A request any operator could reject from the roster and map alone. The text is safe to show."""


def parse_time(text: str) -> float:
    """"2:30" or "T+2:30" to seconds."""
    match = _TIME.match(str(text).strip())
    if not match:
        raise Invalid(f"Bad time {text!r}: use minutes and seconds, such as 2:30 or T+2:30.")
    return int(match[1]) * 60 + int(match[2])


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"T+{total // 60:02d}:{total % 60:02d}"


def parse_grid(text: str, world_size: float) -> tuple[list[float], str]:
    """A 6-digit grid to the centre of its 100 m square, plus its spoken form."""
    match = _GRID.match(str(text))
    if not match:
        raise Invalid(f"Bad grid {text!r}: use six digits, such as 048 190.")
    x, y = int(match[1]) * 100 + 50, int(match[2]) * 100 + 50
    if world_size and not (0 <= x <= world_size and 0 <= y <= world_size):
        raise Invalid(f"Grid {text} is outside the map.")
    return [float(x), float(y)], f"{match[1]} {match[2]}"


def _place(at, markers: dict[str, dict], world_size: float) -> tuple[list[float], str]:
    if isinstance(at, str) and at.strip() in markers:
        return parse_grid(markers[at.strip()]["at"], world_size)
    return parse_grid(at, world_size)


def _enum(value, allowed: set[str], label: str) -> str:
    if value in (None, ""):
        return ""
    upper = str(value).upper()
    if upper not in allowed:
        raise Invalid(f"Bad {label} {value!r}: use one of {', '.join(sorted(allowed))}.")
    return upper


def _number(value, label: str) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        raise Invalid(f"Bad {label} {value!r}.") from None
    if number < 0:
        raise Invalid(f"Bad {label} {value!r}.")
    return number


def validate(request: dict, stations: dict[str, dict], markers: dict[str, dict], world_size: float) -> dict:
    """Check a commander_order request and build what the game side needs: {to, mode, engine_legs, posture, route}."""
    to = request.get("to")
    if to not in stations:
        raise Invalid(f"Unknown callsign {to!r}. See commander_roster.")
    legs = request.get("legs") or []
    if not isinstance(legs, list) or not legs:
        raise Invalid("An order needs at least one leg.")
    posture = [_enum(request.get("speed"), SPEEDS, "speed"), _enum(request.get("formation"), FORMATIONS, "formation"),
               _enum(request.get("behaviour"), BEHAVIOURS, "behaviour"),
               _enum(request.get("combat_mode"), COMBAT_MODES, "combat_mode")]
    mode = str(request.get("mode") or "replace").lower()
    if mode not in ("replace", "append"):
        raise Invalid("Bad mode: use replace or append.")
    types = []
    for leg in legs:
        kind = str(leg.get("type", "")).upper() if isinstance(leg, dict) else ""
        if kind not in ORDER_TYPES:
            raise Invalid(f"Bad order type {kind!r}: use one of {', '.join(sorted(ORDER_TYPES))}.")
        if kind not in stations[to]["capabilities"]:
            raise Invalid(f"{to} can't do {kind}. See commander_roster.")
        types.append(kind)
    if ("HALT" in types or "POSTURE" in types) and len(types) > 1:
        raise Invalid("HALT and POSTURE must be the only leg in an order.")
    if types[0] == "HALT":
        return {"to": to, "mode": "halt", "engine_legs": [], "posture": posture, "route": {"kind": "halt", "legs": []}}
    if types[0] == "POSTURE":
        if posture == ["", "", "", ""]:
            raise Invalid("POSTURE needs at least one setting.")
        return {"to": to, "mode": "posture", "engine_legs": [], "posture": posture, "route": None}
    if "PATROL" in types:
        return _patrol(to, legs, types, posture, markers, world_size)
    engine_legs, route_legs = [], []
    for leg, kind in zip(legs, types, strict=True):
        pos, grid = _place(leg.get("at"), markers, world_size)
        radius, completion = _number(leg.get("radius"), "radius"), _number(leg.get("completion"), "completion")
        hold_for = parse_time(leg["hold_for"]) if leg.get("hold_for") else 0
        engine_legs.append([LEG_TYPES[kind], pos, radius, completion, hold_for])
        route_legs.append({"type": kind, "pos": pos, "grid": grid, "completion": completion})
    return {"to": to, "mode": mode, "engine_legs": engine_legs, "posture": posture,
            "route": {"kind": "route", "legs": route_legs}}


def _patrol(to, legs, types, posture, markers, world_size) -> dict:
    if len(types) > 1:
        raise Invalid("PATROL must be the only leg in an order. Pass its grids as a list in at.")
    points = legs[0].get("at")
    if not isinstance(points, list) or len(points) < 2:
        raise Invalid("PATROL needs a list of at least 2 grids in at.")
    places = [_place(point, markers, world_size) for point in points]
    engine_legs = [["MOVE", pos, 0, 0, 0] for pos, _ in places] + [["CYCLE", places[0][0], 0, 0, 0]]
    route_legs = [{"type": "MOVE", "pos": pos, "grid": grid, "completion": 0} for pos, grid in places]
    return {"to": to, "mode": "replace", "engine_legs": engine_legs, "posture": posture,
            "route": {"kind": "patrol", "legs": route_legs}}
