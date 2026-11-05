"""From perception packets to radio text: rounding, buckets, templates, and deciding what is worth saying.

Pure functions and one small state tracker per station, so all of it can be tested without the game.
Only fields the group could know arrive here (see adapters/commander_boot.sqf), and only rounded words leave.
"""
from __future__ import annotations

import math
import random
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
NEAR_BUILDING_M = 25
COMBAT_RECENT_S = 30  # a squad stays "in combat" this long after its last casualty
UNDER_FIRE_M = 100  # shells this close are the squad's own problem
EXPLOSIONS_M = 400  # and this far off, just something to mention
UNDER_FIRE_QUIET_S = 20  # how long shelling has to stop before it's a new burst
EXPLOSIONS_REPEAT_S = 60
SPLASH_QUIET_S = 4  # a spotter reports this long after the last round of a burst lands
COMBAT_SUPPRESSION = 0.05  # average of getSuppression across the squad, 0 to 1
# How long a squad takes to get a report out, by how suppressed it is on average: (below this, seconds).
REPORT_DELAYS = ((0.1, 5.0), (0.4, 15.0), (math.inf, 30.0))
BEARING_ERROR_DEG = 5  # a soldier's snap estimate, widened by how vaguely the target's position is known
BEARING_ERROR_MAX_DEG = 20
BEARING_ROUND_DEG = 5
DEFAULT_TOPICS = ["position", "task", "strength", "ammo", "contacts", "vehicles"]
PLACING_ORDERS = {"OCCUPY", "CORDON"}
TASK_ORDERS = {"ATTACK", "DEFEND", "PATROL_AREA", "SWEEP"}  # CBA tasks: they run until replaced, with no end to report
SINGLE_LEG_ORDERS = {"CLEAR"} | PLACING_ORDERS | TASK_ORDERS
LEG_VERBS = {"HOLD": "holding at", "SENTRY": "watching at", "SEARCH": "searching around", "OCCUPY": "occupying",
             "CORDON": "setting a cordon around", "ATTACK": "attacking", "DEFEND": "defending",
             "PATROL_AREA": "patrolling around", "SWEEP": "sweeping around"}


def format_grid(grid: str) -> str:
    """Engine grid "052191" to spoken "052 191"."""
    middle = len(grid) // 2
    return f"{grid[:middle]} {grid[middle:]}"


def compass(dx: float, dy: float) -> str:
    bearing = math.degrees(math.atan2(dx, dy)) % 360
    return _COMPASS[round(bearing / 45) % 8]


def _wobble(spread: float) -> float:
    return random.uniform(-spread, spread)


def spoken_bearing(dx: float, dy: float, accuracy_m: float = 0) -> str:
    """A compass bearing as someone would call it out. It's an estimate, so each call can come out differently."""
    spread = min(BEARING_ERROR_MAX_DEG, BEARING_ERROR_DEG + math.degrees(math.atan2(accuracy_m, math.hypot(dx, dy))))
    bearing = math.degrees(math.atan2(dx, dy)) + _wobble(spread)
    return f"bearing {round(bearing / BEARING_ROUND_DEG) * BEARING_ROUND_DEG % 360:03d}"


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
    """Group contacts by compass sector from this group, newest knowledge first. The sector only decides what counts as
    one report. What gets said is a bearing to the nearest contact in it."""
    x, y = packet["pos"]
    groups: dict[str, dict] = {}
    for contact in packet.get("contacts") or []:
        if contact["age_s"] > max_age:
            continue
        dx, dy = contact["pos"][0] - x, contact["pos"][1] - y
        direction = compass(dx, dy)
        entry = groups.setdefault(direction, {"direction": direction, "count": 0, "kinds": {}, "range": math.inf,
                                              "age_s": math.inf, "nearest": contact["pos"], "offset": (dx, dy),
                                              "accuracy_m": contact.get("accuracy_m", 0)})
        entry["count"] += 1
        entry["kinds"][contact["kind"]] = entry["kinds"].get(contact["kind"], 0) + 1
        if math.hypot(dx, dy) < entry["range"]:
            entry["nearest"], entry["offset"] = contact["pos"], (dx, dy)
            entry["accuracy_m"] = contact.get("accuracy_m", 0)
        entry["range"] = min(entry["range"], math.hypot(dx, dy))
        entry["age_s"] = min(entry["age_s"], contact["age_s"])
    return sorted(groups.values(), key=lambda g: g["age_s"])


def contact_phrase(group: dict, buildings: list[dict] | None = None) -> str:
    kind = max(group["kinds"], key=group["kinds"].get)
    label = ("contact" if group["count"] == 1 else "contacts") if kind == "unknown" else kind
    bearing = spoken_bearing(*group["offset"], group["accuracy_m"])
    words = f"{count_word(group['count'])} {label}, {bearing}, {rough_range(group['range'])}"
    nearby = _nearest_building(group.get("nearest"), buildings)
    return f"{words}, near {nearby}" if nearby else words


def _nearest_building(pos: list[float] | None, buildings: list[dict] | None) -> str | None:
    """The numbered building the group believes a contact is at, from its own perceived position."""
    if not pos or not buildings:
        return None
    best = min(buildings, key=lambda b: math.dist(b["pos"], pos))
    return best["id"] if math.dist(best["pos"], pos) <= NEAR_BUILDING_M else None


def remaining_distance(packet: dict, route: dict | None) -> float:
    """Metres left on the route, walking from here through the legs not yet reached."""
    if not route:
        return 0.0
    if route["legs"] and route["legs"][0]["type"] in SINGLE_LEG_ORDERS:
        return math.dist(packet["pos"], route["legs"][0]["pos"])
    points = [leg["pos"] for leg in route["legs"][packet.get("leg", 0):]]
    total, here = 0.0, packet["pos"]
    for point in points:
        total += math.dist(here, point)
        here = point
    return total


def _current_leg(packet: dict, route: dict | None) -> dict | None:
    if not route or not route["legs"]:
        return None
    if route["legs"][0]["type"] in SINGLE_LEG_ORDERS:  # these don't count waypoints the way a route does
        return route["legs"][0]
    leg = packet.get("leg", 0)
    return route["legs"][leg] if 0 <= leg < len(route["legs"]) else None


def report_delay(packet: dict, precedence: str = ROUTINE) -> float:
    """Seconds before a squad in combat gets this out. Shouting "contact" comes quicker than anything else."""
    suppression = packet.get("suppression") or 0
    delay = next(seconds for below, seconds in REPORT_DELAYS if suppression < below)
    delay = delay / 2 if precedence == FLASH else delay
    return max(1.0, delay + _wobble(delay * 0.3))


def answer(packet: dict, route: dict | None, topics: list[str] | None = None,
           buildings: list[dict] | None = None, in_combat: bool = False) -> str:
    """Words for a general SITREP or a specific question, from the group's latest packet. A squad in combat only works
    out its own grid when it's specifically asked for its position."""
    parts = []
    wanted = topics or [topic for topic in DEFAULT_TOPICS if not (in_combat and topic == "position")]
    for topic in wanted:
        match topic:
            case "position":
                moving = packet.get("speed", 0) > 1
                motion = f"moving {_COMPASS[round(packet.get('dir', 0) / 45) % 8]}" if moving else "stationary"
                parts.append(f"Grid {format_grid(packet['grid'])}, {motion}.")
            case "task":
                parts.append(_task_words(packet, route, in_combat))
            case "strength":
                wounded = packet.get("wounded", 0)
                hurt = f", {wounded} wounded" if wounded else ""
                parts.append(f"{packet['alive']} of {packet['baseline']} effective{hurt}. "
                             f"{packet['leader']} has command.")
            case "ammo":
                band = ammo_band(packet.get("rounds", 0), packet.get("rounds_baseline", 0))
                parts.append(f"Ammo {band}, {_AMMO_WORDS[band]}.")
                for gun, ammo in packet.get("gun_ammo") or []:
                    held = ", ".join(f"{count} {word}" for word, count in ammo) or "empty"
                    parts.append(f"{gun or 'The gun'}: {held}.")
            case "contacts":
                groups = contact_groups(packet)
                parts.append(" ".join(f"{_sentence(contact_phrase(g, buildings))}, {age_words(g['age_s'])}."
                                      for g in groups) if groups else "No contacts.")
            case "eta":
                parts.append(_eta_words(packet, route))
            case "vehicles":
                words = _vehicle_words(packet)
                if words or topics:  # a general SITREP doesn't mention being on foot
                    parts.append(words or "All on foot.")
            case _:
                parts.append(f"Can't say about {topic}.")
    return " ".join(parts)


def _vehicle_words(packet: dict) -> str:
    """Who's on what, from packet["mounted"], where the runtime has already put in the commander's own ids."""
    rows = packet.get("mounted") or []
    if not rows:
        return ""
    by_vehicle: dict[str, list[str]] = {}
    for vehicle, seat, name, *_ in rows:  # the rest of a row isn't for saying aloud
        by_vehicle.setdefault(vehicle or "a vehicle", []).append(f"{name} as {seat}")
    words = " ".join(f"On {vehicle}: {', '.join(seats)}." for vehicle, seats in by_vehicle.items())
    on_foot = packet.get("alive", 0) - len(rows)
    return f"{words} {on_foot} on foot." if on_foot > 0 else words


def _sentence(words: str) -> str:
    return words[:1].upper() + words[1:]  # str.capitalize would lower-case a building's id


def _task_words(packet: dict, route: dict | None, in_combat: bool = False) -> str:
    if route and route.get("kind") == "halt":
        return "Halted." if in_combat else f"Halted at grid {format_grid(packet['grid'])}."
    leg = _current_leg(packet, route)
    if leg is None:
        return "No current orders."
    if leg["type"] == "CLEAR":
        ids = leg.get("ids", [])
        left = [building for building in ids if building not in (packet.get("cleared") or [])]
        if not left or packet.get("clearing", -1) == 0:
            return f"Finished checking {', '.join(ids)}." if ids else "Nothing to check."
        return f"Checking {', '.join(left)}."
    if leg["type"] in PLACING_ORDERS:
        if packet.get("placed") == 1:
            return f"In position, {_place_words(leg)}."
        return f"Moving into {leg.get('building')}." if leg["type"] == "OCCUPY" else f"Moving to cordon {_where(leg)}."
    if leg["type"] in TASK_ORDERS:
        return f"{_sentence(LEG_VERBS[leg['type']])} {_where(leg)}."
    distance = math.dist(packet["pos"], leg["pos"])
    if leg["type"] in ("HOLD", "SENTRY") and distance <= (leg.get("completion") or ON_STATION_M):
        return "Holding." if in_combat else f"Holding at grid {format_grid(packet['grid'])}."
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


def _where(leg: dict) -> str:
    return leg["building"] if leg.get("building") else f"grid {leg['grid']}"


def _place_words(leg: dict) -> str:
    return f"occupying {leg.get('building')}" if leg["type"] == "OCCUPY" else f"cordon around {_where(leg)}"


@dataclass
class Report:
    precedence: str
    text: str
    grid: str | None = None  # the group's own position, when the text states it
    checked: str | None = None  # a numbered building the group has been through
    destroyed: str | None = None  # a numbered building it found to be a ruin


def _without_own_grid(report: Report) -> Report:
    """Nobody checks a map or a GPS under fire. Grids of places it was told about are still fine."""
    if not report.grid:
        return report
    text = report.text
    for spoken in (f", at grid {report.grid}", f", grid {report.grid}", f" at grid {report.grid}"):
        text = text.replace(spoken, "")
    return Report(report.precedence, text, None, report.checked, report.destroyed)


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
    checked: list[str] = field(default_factory=list)
    hurt_at: float = -1.0
    mount_said: list = field(default_factory=list)
    gunners: dict[str, str] = field(default_factory=dict)
    gunners_alive: int = 0
    fire_said: dict[str, str] = field(default_factory=dict)
    spotter: bool = False
    impacts: list[dict] = field(default_factory=list)
    noted: int = 0
    shelled_at: float = -1
    explosions_at: float = -1
    no_view_said: list[str] = field(default_factory=list)

    def in_combat(self, packet: dict, now: float) -> bool:
        """From what the engine measures: a fresh enemy contact, being suppressed, casualties just now, or shells
        landing close, which move none of the others. Behaviour isn't used. It stays COMBAT for 35 s after a fight, and
        a commander can order it."""
        hurt_recently = self.hurt_at >= 0 and now - self.hurt_at < COMBAT_RECENT_S
        shelled = self.shelled_at >= 0 and now - self.shelled_at < COMBAT_RECENT_S
        return hurt_recently or shelled or (packet.get("suppression") or 0) >= COMBAT_SUPPRESSION \
            or bool(contact_groups(packet, CONTACT_FRESH_S))

    def update(self, packet: dict, route: dict | None, now: float, buildings: list[dict] | None = None) -> list[Report]:
        out: list[Report] = []
        out += self._order(packet, route, now)
        out += self._contacts(packet, now, buildings)
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
        out += self._boarding(packet)
        out += self._missions(packet)
        out += self._heard_impacts(packet, now)
        return [_without_own_grid(report) for report in out] if self.in_combat(packet, now) else out

    def _heard_impacts(self, packet: dict, now: float) -> list[Report]:
        """Every shell, whoever fired it. No station can tell whose they were, and none ever says."""
        out = []
        new = [row for row in self.impacts[self.noted:] if "smoke" not in row["ammo"].lower()]
        self.noted = len(self.impacts)
        close = [row for row in new if row["distance"] < UNDER_FIRE_M]
        if close:
            nearest = min(close, key=lambda row: row["distance"])
            if self.shelled_at < 0 or nearest["t"] - self.shelled_at >= UNDER_FIRE_QUIET_S:
                metres = max(10, _offset(nearest["distance"]))
                out.append(Report(PRIORITY, f"Under indirect fire, explosions about {metres} m "
                                            f"{compass(nearest['dx'], nearest['dy'])}."))
            self.shelled_at = max(row["t"] for row in close)
        elif new and not (self.spotter and any(row["seen"] for row in new)):  # a spotter's about to say exactly where
            nearest = min(new, key=lambda row: row["distance"])
            recently = self.explosions_at >= 0 and now - self.explosions_at < EXPLOSIONS_REPEAT_S
            shelled = self.shelled_at >= 0 and now - self.shelled_at < UNDER_FIRE_QUIET_S
            if nearest["distance"] < EXPLOSIONS_M and not recently and not shelled:
                self.explosions_at = now
                out.append(Report(ROUTINE, f"Explosions to the {compass(nearest['dx'], nearest['dy'])}, "
                                           f"{rough_range(nearest['distance'])}."))
        if self.impacts and now - self.impacts[-1]["t"] >= SPLASH_QUIET_S:
            if self.spotter:
                out += self._spotted(packet)
            self.impacts, self.noted = [], 0
        return out

    def _spotted(self, packet: dict) -> list[Report]:
        watched = [row for row in self.impacts if row["observer"]]
        seen = [row for row in (watched or self.impacts) if row["seen"]]
        if watched and seen:
            return [Report(PRIORITY, _splash_words(seen, packet))]
        if watched:
            order = watched[0]["order"]
            if order in self.no_view_said:
                return []
            self.no_view_said.append(order)
            return [Report(PRIORITY, "Can't observe. No view of the fall of shot.")]
        if seen:
            x = sum(row["pos"][0] for row in seen) / len(seen)
            y = sum(row["pos"][1] for row in seen) / len(seen)
            dx = sum(row["dx"] for row in seen) / len(seen)
            dy = sum(row["dy"] for row in seen) / len(seen)
            away = max(50, round(math.hypot(dx, dy) / 50) * 50)
            return [Report(ROUTINE, f"Splash seen, grid {int(x / 100):03d} {int(y / 100):03d}, "
                                    f"about {away} m {compass(dx, dy)} of us.")]
        return []

    def _missions(self, packet: dict) -> list[Report]:
        out = []
        for row in packet.get("missions") or []:
            gun, order, state, *_ = row
            fired, want, eta = row[5], row[6], row[7]
            key = f"{order}:{gun}"
            said = self.fire_said.get(key, "")
            if fired > 0 and "shot" not in said and state != "checked":
                seconds = max(5, round(eta / 5) * 5)
                out.append(Report(ROUTINE, f"Shot, {_rounds(want)}, splash in about {seconds} seconds."))
                said += " shot"
            if state != "firing" and f" {state} " not in f"{said} ":
                words = _mission_words(row, packet)
                if words:
                    out.append(Report(ROUTINE, words))
                said += f" {state}"
            self.fire_said[key] = said
        return out

    def _boarding(self, packet: dict) -> list[Report]:
        out = []
        status = packet.get("mount") or []
        if status and status != self.mount_said:
            self.mount_said = list(status)
            words = _boarding_words(status)
            if words:
                out.append(Report(ROUTINE, words))
        gunners = {row[0]: row[2] for row in packet.get("mounted") or [] if row[1] == "gunner"}
        for vehicle in self.gunners:
            if vehicle not in gunners and packet.get("alive", 0) < self.gunners_alive:
                out.append(Report(PRIORITY, f"Gunner down on {vehicle or 'the gun'}."))
        self.gunners, self.gunners_alive = gunners, packet.get("alive", 0)
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
                self.route_done = self.route_done and bool(route.get("keeps_done"))
                out.append(Report(ROUTINE, route.get("acknowledge", "Copy.")))
            else:
                self.leg, self.on_station, self.route_done, self.checked = 0, [], False, []
                words = f"{_acknowledgement(route, grid)}{_who_stays(packet, route)}"
                out.append(Report(ROUTINE, words, grid if _is_stop(route) else None))
        if not route or self.route_done or route.get("kind") != "route":
            return out
        legs = route["legs"]
        if legs[0]["type"] == "CLEAR":
            return out + self._clearing(packet, legs[0], grid)
        if legs[0]["type"] in PLACING_ORDERS:
            if packet.get("placed") == 1:
                self.route_done = True
                out.append(Report(ROUTINE, f"In position, {_place_words(legs[0])}, at grid {grid}.", grid))
            return out
        if legs[0]["type"] in TASK_ORDERS:
            if math.dist(packet["pos"], legs[0]["pos"]) <= max(legs[0].get("radius", 0), ON_STATION_M):
                self.route_done = True
                out.append(Report(ROUTINE, f"On the objective, {LEG_VERBS[legs[0]['type']]} {_where(legs[0])}, at "
                                           f"grid {grid}.", grid))
            return out
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

    def _clearing(self, packet: dict, leg: dict, grid: str) -> list[Report]:
        """Going through buildings isn't proof of anything, so reports say what happened and not "all clear"."""
        out = []
        seen_nearby = bool(contact_groups(packet, CONTACT_FRESH_S))
        for building in packet.get("cleared") or []:
            if building not in self.checked:
                self.checked.append(building)
                result = "enemy still in the area" if seen_nearby else "nothing seen"
                out.append(Report(ROUTINE, f"{building} checked, {result}.", checked=building))
        for building in packet.get("ruined") or []:
            if building not in self.checked:
                self.checked.append(building)
                out.append(Report(ROUTINE, f"{building} is a ruin, nothing to check.", destroyed=building))
        if packet.get("clearing", -1) == 0:
            self.route_done = True
            ids = leg.get("ids", [])
            words = f"Finished checking {', '.join(ids)}, at grid {grid}." if ids else "No known buildings there."
            out.append(Report(ROUTINE, words, grid))
        return out

    def _contacts(self, packet: dict, now: float, buildings: list[dict] | None = None) -> list[Report]:
        fresh = contact_groups(packet, CONTACT_FRESH_S)
        if fresh:
            self.contact_seen = now
            signature = ";".join(f"{g['direction']}:{count_word(g['count'])}" for g in
                                 sorted(fresh, key=lambda g: g["direction"]))
            summary = "; ".join(contact_phrase(g, buildings) for g in fresh)
            action = "Engaging" if packet.get("combat_mode") in ("YELLOW", "RED") else "Holding fire"
            # No grid of their own here: working one out takes a map or a GPS, and nobody's doing that under fire.
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
        if self.alive >= 0 and alive < self.alive:
            self.hurt_at = now
            if self.casualties_since < 0:
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
        moving_order = current is not None and route.get("kind") in ("route", "patrol") and not self.route_done \
            and current["type"] not in ("CLEAR", "PATROL_AREA", "SWEEP", "DEFEND")
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


def _who_stays(packet: dict, route: dict | None) -> str:
    """A man on a static gun stays there when his squad moves off. The engine does that, and it's worth knowing."""
    if not route or route.get("kind") not in ("route", "patrol"):
        return ""
    stays = [row for row in packet.get("mounted") or [] if len(row) > 3 and row[3] and row[2] != packet.get("leader")]
    return "".join(f" {row[2]} stays on {row[0] or 'the gun'}." for row in stays)


def _boarding_words(status: list) -> str | None:
    """What a squad says about getting on or off. Nothing while it's still doing it."""
    vehicle, word, seat, names = status[0] or "the vehicle", status[1], status[2], status[3]
    spare = status[4] if len(status) > 4 else 0
    who = ", ".join(names)
    place = f" as {seat}" if seat else ""
    said = {
        "wrecked": f"{vehicle} is wrecked. Not mounting.",
        "noseat": f"Unable, {vehicle} has no {seat} seat.",
        "taken": f"Unable, {vehicle}'s {seat} seat is taken." if seat else f"Unable, {vehicle} is full.",
        "nobody": f"Unable, nobody free to mount {vehicle}.",
        "unreachable": f"Unable, can't reach {vehicle}.",
        "on": f"{who} on {vehicle}{place}." + (f" {spare} didn't fit." if spare else ""),
        "none": "Nobody's on a vehicle.",
        "off": f"Off {vehicle}.",
    }
    return said.get(word)


def _rounds(count: int) -> str:
    return f"{count} round" if count == 1 else f"{count} rounds"


def _gun_left(packet: dict, gun: str, word: str) -> str:
    for key, ammo in packet.get("gun_ammo") or []:
        if key == gun:
            return f" {dict(ammo).get(word, 0)} {word} left."
    return ""


def _offset(metres: float) -> int:
    """What an observer can call by eye: to 10 m up close, to 50 m beyond that."""
    metres = abs(metres)
    step = 10 if metres < 100 else 50
    return round(metres / step) * step


def _splash_words(rows: list[dict], packet: dict) -> str:
    """Where a burst landed, against the enemy this spotter believes is there, or failing that the grid it was given.
    An offset from the aim alone would be no help if the aim is what's wrong."""
    x = sum(row["pos"][0] for row in rows) / len(rows)
    y = sum(row["pos"][1] for row in rows) / len(rows)
    fresh = [c for c in packet.get("contacts") or [] if c["age_s"] <= CONTACT_FRESH_S]
    if fresh:
        ref = min(fresh, key=lambda c: math.dist(c["pos"], [x, y]))["pos"]
        name = "the enemy"
    else:
        ref, name = rows[0]["aim"], "your grid"
    north, east = _offset(y - ref[1]), _offset(x - ref[0])
    parts = []
    if north:
        parts.append(f"{north} m {'north' if y > ref[1] else 'south'}")
    if east:
        parts.append(f"{east} m {'east' if x > ref[0] else 'west'}")
    where = f"Splash {', '.join(parts)} of {name}." if parts else f"Splash on {name}."
    return f"{where} {_rounds(len(rows))} seen."


def _mission_words(row: list, packet: dict) -> str | None:
    """How a mission's state is said. It's about the gun, and never says what the rounds hit."""
    gun, _, state, reason, word, fired, want, _, in_air = row
    name = gun or "the gun"
    if state == "done":
        return f"Rounds complete.{_gun_left(packet, gun, word)}"
    if state == "out":
        return f"Out of {word}, {fired} of {want} fired."
    if state == "holding":
        return "Holding, weapons tight. Mission waiting."
    if state == "cantlay":
        return "Unable, can't lay on that target."
    if state == "gunner":
        return f"{fired} of {want} fired, no gunner on {name}."
    if state == "destroyed":
        return f"{name} destroyed, {fired} of {want} fired."
    if state == "checked":  # the order's acknowledged by then: this is only what can't be called back
        return f"{_rounds(in_air)} still in the air." if in_air else None
    if state == "unable":
        return {"out of range": "Unable, out of range.", "no gunner": f"Unable, no gunner on {name}.",
                "no gun": "Unable, no gun crewed.", "no ammo": f"Unable, out of {word}.",
                "destroyed": f"Unable, {name} is destroyed."}.get(reason, "Unable.")
    return None


def _acknowledgement(route: dict | None, grid: str) -> str:
    kind = route.get("kind") if route else ""
    if kind == "mount":
        seat = f" as {route['seat']}" if route.get("seat") else ""
        return f"Copy, mounting {route['vehicle']}{seat}."
    if kind == "dismount":
        return f"Copy, getting off {route['vehicle']}." if route.get("vehicle") else "Copy, getting off."
    if kind == "halt":
        return f"Halted at grid {grid}."
    if kind == "posture":
        return "Copy."
    if kind == "patrol":
        return f"Copy, starting patrol from grid {route['legs'][0]['grid']}."
    words = leg_words((route or {}).get("legs", []))
    return f"Copy, {words}." if words else "Copy."


def leg_words(legs: list[dict]) -> str:
    words = []
    for leg in legs:
        if leg["type"] == "CLEAR":
            words.append(f"checking {', '.join(leg.get('ids', []))}" if leg.get("ids") else "checking the area")
        else:
            words.append(f"{LEG_VERBS.get(leg['type'], 'moving to')} {_where(leg)}")
    return ", then ".join(words)


def _finish_words(leg: dict, grid: str) -> str:
    if leg["type"] == "SEARCH":
        return f"Finished searching around grid {leg['grid']}, at grid {grid}."
    if leg["type"] == "SENTRY":
        return f"Enemy spotted while watching grid {leg['grid']}, at grid {grid}."
    return f"Arrived, grid {grid}."
