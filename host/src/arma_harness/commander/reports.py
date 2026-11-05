"""From perception packets to radio text: rounding, buckets, templates, and deciding what is worth saying.

Pure functions and one small state tracker per station, so all of it can be tested without the game.
Only fields the group could know arrive here (see adapters/commander_boot.sqf), and only rounded words leave.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

FLASH, PRIORITY, ROUTINE = "flash", "priority", "routine"

_COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
_AMMO_BANDS = ["green", "amber", "red", "black"]
_AMMO_WORDS = {"green": "good", "amber": "about half", "red": "low", "black": "almost out"}

CONTACT_FRESH_S = 30
CONTACT_LOST_S = 120
CONTACT_FORGOTTEN_S = 300
CONTACT_UPDATE_S = 90
CASUALTY_GROUP_S = 30
STUCK_AFTER_S = 120
STUCK_REPEAT_S = 180
STUCK_MIN_M = 20
ON_STATION_M = 30
DEFAULT_TOPICS = ["position", "task", "strength", "ammo", "contacts"]


def format_grid(grid: str) -> str:
    """Engine grid "052191" to spoken "052 191"."""
    middle = len(grid) // 2
    return f"{grid[:middle]} {grid[middle:]}"


def compass(dx: float, dy: float) -> str:
    bearing = math.degrees(math.atan2(dx, dy)) % 360
    return _COMPASS[round(bearing / 45) % 8]


def rough_range(metres: float) -> str:
    if metres >= 1500:
        return "distant"
    step = 50 if metres <= 500 else 100
    return f"roughly {max(step, round(metres / step) * step)} metres"


def count_word(n: int) -> str:
    if n <= 2:
        return {1: "one", 2: "a couple of"}.get(n, "no")
    if n <= 5:
        return "a few"
    if n <= 9:
        return "about 8"
    return "a dozen" if n <= 14 else "many"


def age_words(seconds: float) -> str:
    if seconds < CONTACT_FRESH_S:
        return "seen now"
    if seconds < 90:
        return "last seen a minute ago"
    return f"last seen {round(seconds / 60)} minutes ago"


def ammo_band(rounds: float, baseline: float) -> str:
    ratio = rounds / baseline if baseline > 0 else 1.0
    if ratio >= 0.66:
        return "green"
    if ratio >= 0.33:
        return "amber"
    return "red" if ratio >= 0.05 else "black"


def contact_groups(packet: dict, max_age: float = CONTACT_FORGOTTEN_S) -> list[dict]:
    """Group contacts by direction from this group, newest knowledge first."""
    x, y = packet["pos"]
    groups: dict[str, dict] = {}
    for contact in packet.get("contacts") or []:
        if contact["age_s"] > max_age:
            continue
        dx, dy = contact["pos"][0] - x, contact["pos"][1] - y
        direction = compass(dx, dy)
        entry = groups.setdefault(direction, {"direction": direction, "count": 0, "kinds": {}, "range": math.inf,
                                              "age_s": math.inf})
        entry["count"] += 1
        entry["kinds"][contact["kind"]] = entry["kinds"].get(contact["kind"], 0) + 1
        entry["range"] = min(entry["range"], math.hypot(dx, dy))
        entry["age_s"] = min(entry["age_s"], contact["age_s"])
    return sorted(groups.values(), key=lambda g: g["age_s"])


def contact_phrase(group: dict) -> str:
    kind = max(group["kinds"], key=group["kinds"].get)
    label = "contacts" if kind == "unknown" else kind
    return f"{count_word(group['count'])} {label}, {group['direction']}, {rough_range(group['range'])}"


def remaining_distance(packet: dict, route: dict | None) -> float:
    """Metres left on the route, walking from here through the legs not yet reached."""
    if not route:
        return 0.0
    points = [leg["pos"] for leg in route["legs"][packet.get("leg", 0):]]
    total, here = 0.0, packet["pos"]
    for point in points:
        total += math.dist(here, point)
        here = point
    return total


def _current_leg(packet: dict, route: dict | None) -> dict | None:
    if not route or not route["legs"]:
        return None
    leg = packet.get("leg", 0)
    return route["legs"][leg] if 0 <= leg < len(route["legs"]) else None


def answer(packet: dict, route: dict | None, topics: list[str] | None = None) -> str:
    """Words for a general SITREP or a specific question, from the group's latest packet."""
    parts = []
    for topic in topics or DEFAULT_TOPICS:
        match topic:
            case "position":
                moving = packet.get("speed", 0) > 1
                motion = f"moving {_COMPASS[round(packet.get('dir', 0) / 45) % 8]}" if moving else "stationary"
                parts.append(f"Grid {format_grid(packet['grid'])}, {motion}.")
            case "task":
                parts.append(_task_words(packet, route))
            case "strength":
                wounded = packet.get("wounded", 0)
                hurt = f", {wounded} wounded" if wounded else ""
                parts.append(f"{packet['alive']} of {packet['baseline']} effective{hurt}. "
                             f"{packet['leader']} has command.")
            case "ammo":
                band = ammo_band(packet.get("rounds", 0), packet.get("rounds_baseline", 0))
                parts.append(f"Ammo {band}, {_AMMO_WORDS[band]}.")
            case "contacts":
                groups = contact_groups(packet)
                parts.append(" ".join(f"{contact_phrase(g).capitalize()}, {age_words(g['age_s'])}." for g in groups)
                             if groups else "No contacts.")
            case "eta":
                parts.append(_eta_words(packet, route))
            case _:
                parts.append(f"Can't say about {topic}.")
    return " ".join(parts)


def _task_words(packet: dict, route: dict | None) -> str:
    if route and route.get("kind") == "halt":
        return f"Halted at grid {format_grid(packet['grid'])}."
    leg = _current_leg(packet, route)
    if leg is None:
        return "No current orders."
    distance = math.dist(packet["pos"], leg["pos"])
    if leg["type"] in ("HOLD", "SENTRY") and distance <= (leg.get("completion") or ON_STATION_M):
        return f"Holding at grid {format_grid(packet['grid'])}."
    verb = {"HOLD": "Moving to hold at", "SENTRY": "Moving to watch at", "SEARCH": "Searching around"}.get(
        leg["type"], "Moving to")
    return f"{verb} grid {leg['grid']}, {rough_range(distance).replace('roughly', 'about')} out."


def _eta_words(packet: dict, route: dict | None) -> str:
    distance = remaining_distance(packet, route)
    leg = _current_leg(packet, route)
    if leg is None or distance < ON_STATION_M:
        return "No movement planned."
    speed = max(packet.get("speed", 0) / 3.6, 2.5) if packet.get("speed", 0) > 1 else 3.0
    minutes = max(1, math.ceil(distance / speed / 60))
    unit = "minute" if minutes == 1 else "minutes"
    return f"About {minutes} {unit} to grid {route['legs'][-1]['grid']}, if unopposed."


@dataclass
class Report:
    precedence: str
    text: str
    grid: str | None = None  # the group's own position, when the text states it


@dataclass
class Tracker:
    """What a station has already said. Plain data, so it can be saved between server restarts."""
    order: str = ""
    leg: int = 0
    on_station: list[int] = field(default_factory=list)
    route_done: bool = False
    alive: int = -1
    casualties_since: float = -1.0
    leader: str = ""
    ammo: str = ""
    contact_active: bool = False
    contact_seen: float = -1.0
    contact_signature: str = ""
    contact_said: float = -1.0
    progress_pos: list[float] = field(default_factory=list)
    progress_t: float = -1.0
    stuck_said: float = -1.0

    def update(self, packet: dict, route: dict | None, now: float) -> list[Report]:
        out: list[Report] = []
        out += self._order(packet, route, now)
        out += self._contacts(packet, now)
        out += self._casualties(packet, now)
        if self.leader and packet["leader"] != self.leader:
            out.append(Report(PRIORITY, f"Leader down, {packet['leader']} has command."))
        self.leader = packet["leader"]
        band = ammo_band(packet.get("rounds", 0), packet.get("rounds_baseline", 0))
        if self.ammo and _AMMO_BANDS.index(band) > _AMMO_BANDS.index(self.ammo):
            out.append(Report(PRIORITY, f"Ammo {band}, {_AMMO_WORDS[band]}."))
        if not self.ammo or _AMMO_BANDS.index(band) > _AMMO_BANDS.index(self.ammo):
            self.ammo = band
        out += self._stuck(packet, route, now)
        return out

    def _order(self, packet: dict, route: dict | None, now: float) -> list[Report]:
        order, grid = packet.get("order", ""), format_grid(packet["grid"])
        out = []
        if order and order != self.order:
            self.order = order
            self.progress_pos, self.progress_t = list(packet["pos"]), now
            if packet.get("unable"):
                self.route_done = True
                return [Report(ROUTINE, "Unable, that grid is open water.")]
            if route and route.get("keeps_progress") == order:
                # POSTURE and appended legs continue the route, so its numbering carries on.
                self.route_done = self.route_done and route.get("acknowledge") == "Copy."
                out.append(Report(ROUTINE, route.get("acknowledge", "Copy.")))
            else:
                self.leg, self.on_station, self.route_done = 0, [], False
                out.append(Report(ROUTINE, _acknowledgement(route, grid), grid if _is_stop(route) else None))
        if not route or self.route_done or route.get("kind") != "route":
            return out
        legs = route["legs"]
        leg_now = packet.get("leg", 0)
        while self.leg < leg_now and self.leg < len(legs):
            if self.leg == len(legs) - 1:
                out.append(Report(ROUTINE, _finish_words(legs[self.leg], grid), grid))
                self.route_done = True
            elif legs[self.leg]["grid"] != legs[self.leg + 1]["grid"]:  # moving somewhere to hold there is one trip
                out.append(Report(ROUTINE, f"Passing grid {legs[self.leg]['grid']}, at grid {grid}.", grid))
            self.leg += 1
        current = _current_leg(packet, route)
        if current and current["type"] in ("HOLD", "SENTRY") and leg_now not in self.on_station \
                and math.dist(packet["pos"], current["pos"]) <= (current.get("completion") or ON_STATION_M):
            self.on_station.append(leg_now)
            words = "On station" if current["type"] == "HOLD" else "In position, watching"
            out.append(Report(ROUTINE, f"{words}, grid {grid}.", grid))
        return out

    def _contacts(self, packet: dict, now: float) -> list[Report]:
        fresh = contact_groups(packet, CONTACT_FRESH_S)
        if fresh:
            self.contact_seen = now
            signature = ";".join(f"{g['direction']}:{count_word(g['count'])}" for g in
                                 sorted(fresh, key=lambda g: g["direction"]))
            summary = "; ".join(contact_phrase(g) for g in fresh)
            action = "Engaging" if packet.get("combat_mode") in ("YELLOW", "RED") else "Holding fire"
            if not self.contact_active:
                self.contact_active, self.contact_signature, self.contact_said = True, signature, now
                return [Report(FLASH, f"Contact, {summary}. {action}.")]
            if signature != self.contact_signature and now - self.contact_said >= CONTACT_UPDATE_S:
                self.contact_signature, self.contact_said = signature, now
                return [Report(PRIORITY, f"Contact update, {summary}.")]
            return []
        if self.contact_active and now - self.contact_seen >= CONTACT_LOST_S:
            self.contact_active, self.contact_signature = False, ""
            return [Report(ROUTINE, "Lost contact.")]
        return []

    def _casualties(self, packet: dict, now: float) -> list[Report]:
        alive = packet["alive"]
        out = []
        if self.alive >= 0 and alive < self.alive and self.casualties_since < 0:
            self.casualties_since = now
        self.alive = alive
        if self.casualties_since >= 0 and now - self.casualties_since >= CASUALTY_GROUP_S:
            self.casualties_since = -1.0
            wounded = packet.get("wounded", 0)
            hurt = f", {wounded} wounded" if wounded else ""
            out.append(Report(PRIORITY, f"Taking casualties, {alive} of {packet['baseline']} effective{hurt}."))
        return out

    def _stuck(self, packet: dict, route: dict | None, now: float) -> list[Report]:
        current = _current_leg(packet, route)
        moving_order = current is not None and route.get("kind") in ("route", "patrol") and not self.route_done
        arrived = current is not None and packet.get("leg", 0) in self.on_station
        if not moving_order or arrived or self.contact_active or not self.progress_pos:
            self.progress_pos, self.progress_t = list(packet["pos"]), now
            return []
        if math.dist(packet["pos"], self.progress_pos) >= STUCK_MIN_M:
            self.progress_pos, self.progress_t = list(packet["pos"]), now
            return []
        if now - self.progress_t >= STUCK_AFTER_S and (self.stuck_said < 0 or now - self.stuck_said >= STUCK_REPEAT_S):
            self.stuck_said = now
            grid = format_grid(packet["grid"])
            return [Report(PRIORITY, f"Not making progress toward grid {current['grid']}, at grid {grid}.", grid)]
        return []


def _is_stop(route: dict | None) -> bool:
    return bool(route) and route.get("kind") == "halt"


def _acknowledgement(route: dict | None, grid: str) -> str:
    kind = route.get("kind") if route else ""
    if kind == "halt":
        return f"Halted at grid {grid}."
    if kind == "posture":
        return "Copy."
    if kind == "patrol":
        return f"Copy, starting patrol from grid {route['legs'][0]['grid']}."
    words = leg_words((route or {}).get("legs", []))
    return f"Copy, {words}." if words else "Copy."


def leg_words(legs: list[dict]) -> str:
    verbs = {"HOLD": "holding at", "SENTRY": "watching at", "SEARCH": "searching around"}
    return ", then ".join(f"{verbs.get(leg['type'], 'moving to')} grid {leg['grid']}" for leg in legs)


def _finish_words(leg: dict, grid: str) -> str:
    if leg["type"] == "SEARCH":
        return f"Finished searching around grid {leg['grid']}, at grid {grid}."
    if leg["type"] == "SENTRY":
        return f"Enemy spotted while watching grid {leg['grid']}, at grid {grid}."
    return f"Arrived, grid {grid}."
