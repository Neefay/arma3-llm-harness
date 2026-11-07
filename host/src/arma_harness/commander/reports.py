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
MOVING_OVER_S = 30  # a squad in contact goes in stops and starts, so one moment says nothing about whether it's moving
MOVING_M = 15  # more than soldiers shuffle about in that time
COMBAT_SUPPRESSION = 0.05  # average of getSuppression across the squad, 0 to 1
# How long a squad takes to get a report out, by how suppressed it is on average: (below this, seconds).
REPORT_DELAYS = ((0.1, 5.0), (0.4, 15.0), (math.inf, 30.0))
BEARING_ERROR_DEG = 5  # a soldier's snap estimate, widened by how vaguely the target's position is known
BEARING_ERROR_MAX_DEG = 20
BEARING_ROUND_DEG = 5
DEFAULT_TOPICS = ["position", "task", "strength", "casualties", "ammo", "contacts", "vehicles"]
LEFT_BEHIND_M = 150  # a squad further than this from one of its own who's down has left him
APART_M = 100  # a man on his feet further than this from his leader isn't with the squad, whatever the count says
TOGETHER_M = 50  # and he's back when this close, so someone walking along at the edge doesn't keep coming and going
APART_SAID_AFTER_S = 30  # a squad on the move strings out, and that isn't news
# How fast things go in m/s, measured on the real game: see host/tests/spikes/move_lag. For saying how long a move will
# take. A squad of 8 on open ground, by behaviour then speed. Behaviour matters far more than speed.
PACE_ON_FOOT = {"CARELESS": {"LIMITED": 1.5, "NORMAL": 2.0, "FULL": 1.8},
                "SAFE": {"LIMITED": 1.5, "NORMAL": 1.7, "FULL": 1.8},
                "AWARE": {"LIMITED": 1.4, "NORMAL": 4.1, "FULL": 4.1},
                "COMBAT": {"LIMITED": 1.1, "NORMAL": 1.6, "FULL": 1.3},
                "STEALTH": {"LIMITED": 1.0, "NORMAL": 1.0, "FULL": 1.3}}
PACE_DRIVING = 18.0
PACE_CARRYING = 1.7
PACE_LIMPING = 1.1
CARRY_LIFT_S = 20
ESTIMATE_FROM_M = 100  # nearer than this, there's nothing worth saying
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
                moving = packet.get("speed", 0) > 1 or packet.get("under_way")
                motion = f"moving {_COMPASS[round(packet.get('dir', 0) / 45) % 8]}" if moving else "stationary"
                parts.append(f"Grid {format_grid(packet['grid'])}, {motion}.")
            case "task":
                parts.append(_task_words(packet, route, in_combat))
            case "strength":
                parts.append(f"{packet['alive']} of {packet['baseline']} effective{_hurt_words(packet)}."
                             f"{_legs_words(packet)}{_apart_words(packet)} "
                             f"{packet['leader']} has command.")
            case "casualties":
                words = _casualty_words(packet)
                if words or topics:
                    parts.append(words or "No casualties.")
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


def _apart_words(packet: dict) -> str:
    """A full count doesn't mean they're all here: a treated man walks back by himself, however far that is."""
    far = [f"{name}, about {_offset(math.hypot(dx, dy))} m {compass(dx, dy)}"
           for name, dx, dy, _busy in packet.get("spread") or [] if math.hypot(dx, dy) >= APART_M]
    return f" Not with us: {', and '.join(far)}." if far else ""


def _hurt_words(packet: dict) -> str:
    down = sum(row["own"] for row in packet.get("casualties") or [])
    wounded = packet.get("wounded", 0)
    return (f", {down} down" if down else "") + (f", {wounded} wounded" if wounded else "")


def _casualty_words(packet: dict) -> str:
    """Who's down that this squad knows about, and roughly where from here."""
    parts = []
    for row in packet.get("casualties") or []:
        if row["vehicle"]:
            where = f"on {row['vehicle']}"
        else:
            away = math.hypot(row["dx"], row["dy"])
            where = "right here" if away < 15 else f"about {_offset(away)} m {compass(row['dx'], row['dy'])}"
        parts.append(f"{row['id']} {row['name']}, down, {where}.")
    return " ".join(parts)


# What tells the commander where a man has ended up: he's where it sent him, or at the vehicle it named.
_CARE_SAYS_WHERE = {("carry", "carried"), ("carry", "placed"), ("carry", "loaded"), ("carry", "loaded directly"),
                    ("carry", "stuck"), ("carry", "put down"), ("unload", "off")}
_CARE_WORDS = {
    ("carry", "carrying"): "Got {name}, on the way.",
    ("carry", "carried"): "Set {name} down.",
    ("carry", "placed"): "Set {name} down.",
    ("carry", "loaded"): "{name}'s loaded.",
    ("carry", "loaded directly"): "{name}'s loaded.",
    ("carry", "couldn't load him"): "Couldn't load {name}, there's no room.",
    ("carry", "he died"): "{name}'s dead.",
    ("carry", "he woke"): "{name}'s back up.",
    ("carry", "medic down"): "Lost the man carrying {name}.",
    ("carry", "can't reach him"): "Can't get to {name}.",
    ("carry", "stuck"): "Got stuck with {name}, set down short.",
    ("carry", "put down"): "Put {name} down.",
    ("carry", "left"): "Leaving {name} where they are.",
    ("carry", "aboard"): "{name}'s on {detail}. Get them off first.",
    ("carry", "already"): "{name}'s already being moved.",
    ("carry", "no bearer"): "Nobody free to carry {name}.",
    ("carry", "nobody down"): "Nobody down here.",
    ("carry", "wrecked"): "Unable, {detail} is wrecked.",
    ("unload", "off"): "{name}'s off {detail}.",
    ("unload", "stuck"): "Can't get {name} off {detail}.",
    ("unload", "moving"): "{detail} has to stop first.",
    ("unload", "nobody there"): "Unable, nobody at {detail}.",
    ("unload", "nobody aboard"): "Nobody down on {detail}.",
    ("unload", "not aboard"): "{name} isn't on {detail}.",
    ("unload", "wrecked"): "Unable, {detail} is wrecked.",
    ("treat", "treating"): "Treating {name}.",
    ("treat", "up"): "{name}'s back up.",
    ("treat", "he died"): "{name}'s dead.",
    ("treat", "medic down"): "Lost the medic treating {name}.",
    ("treat", "no medic"): "Unable, no medic here.",
    ("treat", "nobody down"): "Nobody down here.",
    ("treat", "called off"): "Stopped treating {name}.",
    ("treat", "aboard"): "{name}'s on {detail}, which isn't a medical vehicle. We'll treat them when they're off.",
    ("treat", "can't find"): "Can't find {name}.",
    ("treat", "can't reach"): "Can't get to {name}.",
    ("post", "building"): "Setting up the aid post.",
    ("post", "up"): "Aid post up, grid {grid}. Listed as {detail}.",
    ("post", "called off"): "Stopped setting up the aid post.",
    ("post", "have one"): "Unable, we've already got a post up.",
    ("post", "no medic"): "Unable, no medic here.",
    ("post", "medic down"): "Lost the medic setting up the post.",
    ("post", "can't reach"): "Can't get to that spot for the post.",
    ("joined", "joined"): "{name}'s with us now. There's nobody left to go back to.",
}


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
    far = rough_range(distance).replace("roughly", "about") if distance < 1500 else f"about {_distance_words(distance)}"
    return f"{verb} grid {leg['grid']}, {far} out."


def _time_words(seconds: float) -> str:
    minutes = seconds / 60
    if minutes < 1:
        return "under a minute"
    if minutes < 1.5:
        return "about a minute"
    return f"about {5 * round(minutes / 5) if minutes >= 20 else round(minutes)} minutes"


def _distance_words(metres: float) -> str:
    if metres < 950:
        return f"{round(metres, -2):.0f} m"
    return f"{round(metres / 500) / 2:g} km"


def estimate(metres: float, pace: float, how: str, in_combat: bool = False, extra_s: float = 0) -> str:
    """How far and how long, as a squad would say it when it gets an order. It's a guess, and a fight makes it worse."""
    if metres < ESTIMATE_FROM_M:
        return ""
    time_words = _time_words(metres / pace + extra_s)
    if in_combat:
        words = time_words.replace("about", "at least")
        return f" {words[:1].upper()}{words[1:]} {how}, under fire."
    return f" That's {_distance_words(metres)} {how}, {time_words}."


# Whether one step of a chained order is over, and whether it worked. A squad that can't do a step stops there: going
# on would have the truck leave without the men it was meant to wait for.
_CARE_PENDING = {("carry", "going"), ("carry", "carrying"), ("unload", "going"), ("treat", "queued"),
                 ("treat", "going"), ("treat", "treating"), ("treat", "aboard"), ("treat", "medic down"),
                 ("post", "going"), ("post", "building")}
_CARE_FAILED = {("carry", "wrecked"), ("carry", "no bearer"), ("carry", "can't reach him"), ("carry", "stuck"),
                ("carry", "couldn't load him"), ("carry", "medic down"), ("carry", "aboard"), ("carry", "already"),
                ("unload", "stuck"), ("unload", "moving"), ("unload", "nobody there"), ("unload", "wrecked"),
                ("treat", "no medic"), ("treat", "can't find"), ("treat", "can't reach"), ("post", "no medic"),
                ("post", "medic down"), ("post", "can't reach")}
_CARE_MODES = {"carry", "unload", "treat", "post"}


def step_outcome(mode: str, order: str, packet: dict, route_done: bool) -> str | None:
    """"done", "failed", or None while it's still going."""
    if mode in ("mount", "dismount"):
        word = (packet.get("mount") or ["", ""])[1]
        if word in ("on", "off", "none"):
            return "done"
        return None if word in ("going", "going off", "") else "failed"
    if mode in _CARE_MODES:
        rows = [(row[1], row[4]) for row in packet.get("medical") or [] if row[0] == order]
        if not rows or any(row in _CARE_PENDING for row in rows):
            return None
        return "failed" if any(row in _CARE_FAILED for row in rows) else "done"
    if packet.get("unable"):
        return "failed"
    return "done" if route_done else None


def step_words(checked: dict) -> str:
    """One step as part of a longer order, such as "moving to grid 040 060"."""
    words = checked.get("words") or _acknowledgement(checked.get("route"), "")
    return words.removeprefix("Copy, ").removesuffix(".")


def stepped(words: str, then: bool, dropping: str) -> str:
    """A later step isn't a new order, and an order that replaces a chain says what's no longer going to happen."""
    if then:
        words = words.replace("Copy, ", "Now ", 1)
    return f"{words} Dropping the rest: {dropping}." if dropping else words


def foot_pace(packet: dict, speed: str = "", behaviour: str = "") -> float:
    """How quickly it walks, as it's set now, or as an order's about to set it."""
    by_speed = PACE_ON_FOOT.get(behaviour or packet.get("behaviour"), PACE_ON_FOOT["AWARE"])
    return by_speed.get(speed or packet.get("speed_mode"), by_speed["NORMAL"])


def pace_of(packet: dict) -> tuple[float, str]:
    """How quickly this squad would get there, and how to say it. A leader in a vehicle has the squad with him, and one
    who's hit in the legs sets the pace for all of them."""
    leader = packet.get("leader")
    riding = [row for row in packet.get("mounted") or [] if len(row) > 3 and row[2] == leader and not row[3]]
    # All aboard for the trip, even if still climbing in. Haiku was told 16 minutes on foot, for a 3 minute drive.
    boarding = packet.get("mount") or []
    if riding or (len(boarding) > 2 and boarding[1] == "going" and not boarding[2]):
        return PACE_DRIVING, "by vehicle"
    if leader in (packet.get("limping") or []):
        return min(PACE_LIMPING, foot_pace(packet)), f"on foot, with {leader} hit in the legs"
    return foot_pace(packet), "on foot"


def _eta_words(packet: dict, route: dict | None) -> str:
    distance = remaining_distance(packet, route)
    leg = _current_leg(packet, route)
    if leg is None or distance < ON_STATION_M:
        return "No movement planned."
    return f"{_sentence(_time_words(distance / pace_of(packet)[0]))} to grid {route['legs'][-1]['grid']}, if unopposed."


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
    limping: list[str] = field(default_factory=list)
    downs: dict[str, dict] = field(default_factory=dict)
    care_said: dict[str, str] = field(default_factory=dict)
    apart: dict[str, dict] = field(default_factory=dict)
    gone: list[str] = field(default_factory=list)  # who the runtime should take off the list after this update
    located: list[str] = field(default_factory=list)  # casualties whose place the commander has just been told
    trail: list[list] = field(default_factory=list)
    trail_leader: str = ""

    def note_movement(self, packet: dict) -> None:
        """Whether it's been getting anywhere lately, and which way, for when it's asked at a moment it's paused."""
        now, pos = packet["t"], packet.get("pos")
        if not pos:
            return
        if packet.get("leader") != self.trail_leader:  # a new leader is somewhere else, without anyone having moved
            self.trail, self.trail_leader = [], packet.get("leader") or ""
        self.trail = [row for row in self.trail if now - row[0] <= MOVING_OVER_S] + [[now, pos[0], pos[1]]]
        dx, dy = pos[0] - self.trail[0][1], pos[1] - self.trail[0][2]
        packet["under_way"] = math.hypot(dx, dy) >= MOVING_M
        if packet["under_way"] and packet.get("speed", 0) <= 1:
            packet["dir"] = math.degrees(math.atan2(dx, dy)) % 360

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
        out += self._new_limps(packet)
        out += self._downed(packet, now)
        out += self._apart(packet, route, now)
        out += self._care(packet)
        return [_without_own_grid(report) for report in out] if self.in_combat(packet, now) else out

    def _how_long(self, packet: dict, route: dict | None, now: float) -> str:
        if not route:
            return ""
        pace, how = pace_of(packet)
        in_combat = self.in_combat(packet, now)
        if route.get("kind") == "mount" and any(row[0] == route.get("vehicle") for row in packet.get("mounted") or []):
            return ""  # some of them are on it already, wherever the commander's list last had it
        if route.get("kind") == "mount" and route.get("walk_to"):
            return estimate(math.dist(packet["pos"], route["walk_to"]), foot_pace(packet), "on foot", in_combat)
        if route.get("kind") == "patrol" and route.get("legs"):
            return estimate(math.dist(packet["pos"], route["legs"][0]["pos"]), pace, how, in_combat)
        if route.get("kind") != "route" or not route.get("legs") or "pos" not in route["legs"][0]:
            return ""
        return estimate(remaining_distance(packet, route), pace, how, in_combat)

    def _downed(self, packet: dict, now: float) -> list[Report]:
        """Who it knows is down. A squad that's left one of its own behind can't say what's become of him."""
        out, rows = [], {row["id"]: row for row in packet.get("casualties") or []}
        in_combat = self.in_combat(packet, now)
        self.gone = []
        self.located = []
        for one, row in rows.items():
            away = math.hypot(row["dx"], row["dy"])
            known = self.downs.get(one)
            if known is None and (row["own"] or row["new"]):
                where = "" if in_combat or row["vehicle"] else f", grid {row['grid']}"
                said = f"{row['name']}'s down{where}." if row["own"] else f"Found {row['name']} down{where}."
                out.append(Report(PRIORITY, f"{said} Listed as {one}."))
                if where:
                    self.located.append(one)
                known = {"name": row["name"], "left": False}
            if known is None:
                continue
            with_us = row["vehicle"] or row["handled"]
            if row["own"] and not with_us and away > LEFT_BEHIND_M and not known["left"]:
                out.append(Report(ROUTINE, f"We've left {row['name']}, about {_offset(away)} m "
                                           f"{compass(row['dx'], row['dy'])} of us."))
                known["left"] = True
            elif away <= LEFT_BEHIND_M:
                known["left"] = False
            known["near"] = away <= LEFT_BEHIND_M or bool(row["vehicle"])
            self.downs[one] = known
        up = packet.get("up") or []
        for one in [one for one in self.downs if one not in rows]:
            known = self.downs.pop(one)
            if one in up:
                self.gone.append(one)
                out.append(Report(ROUTINE, self._back_up(known["name"], packet, now)))
            elif known.get("near"):
                self.gone.append(one)
                out.append(Report(PRIORITY, f"{known['name']}'s dead."))
            # Otherwise nobody near him knows, so the commander doesn't either: he stays on its list as he was.
        return out

    def _back_up(self, name: str, packet: dict, now: float) -> str:
        for one, dx, dy, _busy in packet.get("spread") or []:
            if one == name and math.hypot(dx, dy) >= APART_M:
                self.apart[name] = {"since": now, "said": True}
                return f"{name}'s back on their feet, about {_offset(math.hypot(dx, dy))} m {compass(dx, dy)} of us."
        return f"{name}'s back on their feet."

    def _apart(self, packet: dict, route: dict | None, now: float) -> list[Report]:
        """Who's got separated from the squad, and when they're back. Men sent off on a job, or spread out by the order
        they're on, aren't news. Someone who drops out of the list has gone down or got in a vehicle, which is said
        elsewhere."""
        leg = _current_leg(packet, route)
        if leg and leg["type"] in SINGLE_LEG_ORDERS:
            self.apart = {}
            return []
        out, rows = [], packet.get("spread") or []
        for name, dx, dy, busy in rows:
            away = math.hypot(dx, dy)
            known = self.apart.get(name)
            if away < TOGETHER_M:
                if known and known["said"]:
                    out.append(Report(ROUTINE, f"{name}'s back with the squad."))
                self.apart.pop(name, None)
            elif away >= APART_M and not busy:
                known = known or self.apart.setdefault(name, {"since": now, "said": False})
                if not known["said"] and now - known["since"] >= APART_SAID_AFTER_S:
                    out.append(Report(ROUTINE, f"{name}'s away from the squad, about {_offset(away)} m "
                                               f"{compass(dx, dy)} of us."))
                    known["said"] = True
        names = {row[0] for row in rows}
        self.apart = {name: known for name, known in self.apart.items() if name in names}
        return out

    def _care(self, packet: dict) -> list[Report]:
        out = []
        for order, kind, one, name, state, detail, grid in packet.get("medical") or []:
            key = f"{order}:{kind}:{one}"
            if self.care_said.get(key) == state:
                continue
            self.care_said[key] = state
            if (kind, state) in _CARE_SAYS_WHERE:
                self.located.append(one)
            words = _CARE_WORDS.get((kind, state))
            if words:
                bad = state not in ("carrying", "carried", "loaded", "treating", "up", "off", "building")
                out.append(Report(PRIORITY if bad else ROUTINE, words.format(name=name, detail=detail, grid=grid)))
        return out

    def _new_limps(self, packet: dict) -> list[Report]:
        names = packet.get("limping") or []
        out = []
        for name in names:
            if name not in self.limping:
                if name == packet.get("leader"):
                    out.append(Report(PRIORITY, f"Slow going, {name}'s hit in the legs."))
                else:
                    out.append(Report(ROUTINE, f"{name}'s hit in the legs."))
        self.limping = list(names)
        return out

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
                said = route.get("acknowledge", "Copy.")
                if said.startswith("Copy, then"):  # more legs on the end of its route
                    said += self._how_long(packet, route, now)
                out.append(Report(ROUTINE, said))
            else:
                self.leg, self.on_station, self.route_done, self.checked = 0, [], False, []
                words = (route or {}).get("says") or (
                    _acknowledgement(route, grid) + _who_stays(packet, route) + self._how_long(packet, route, now))
                words = stepped(words, bool((route or {}).get("then")), (route or {}).get("dropping", ""))
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
                out.append(Report(ROUTINE, _finish_words(legs[self.leg], grid) + _apart_words(packet), grid))
                self.route_done = True
            elif legs[self.leg]["grid"] != legs[self.leg + 1]["grid"]:  # moving somewhere to hold there is one trip
                out.append(Report(ROUTINE, f"Passing grid {legs[self.leg]['grid']}, at grid {grid}.", grid))
            self.leg += 1
        current = _current_leg(packet, route)
        if current and current["type"] in ("HOLD", "SENTRY") and leg_now not in self.on_station \
                and math.dist(packet["pos"], current["pos"]) <= (current.get("completion") or ON_STATION_M):
            self.on_station.append(leg_now)
            words = "On station" if current["type"] == "HOLD" else "In position, watching"
            out.append(Report(ROUTINE, f"{words}, grid {grid}.{_apart_words(packet)}", grid))
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
            out.append(Report(PRIORITY, f"Taking casualties, {alive} of {packet['baseline']} effective"
                                        f"{_hurt_words(packet)}."))
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
        "stuck": f"Can't get {who} off {vehicle}.",
    }
    return said.get(word)


def _legs_words(packet: dict) -> str:
    """A leg wound is the one that changes what a squad can do: at 0.5 and over a man walks at about 1 m/s, and a leader
    sets the pace for all of them. canStand stays true at 0.9, and a bare count of wounded doesn't say."""
    names = packet.get("limping") or []
    return f" {' and '.join(names)} hit in the legs." if names else ""


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
        # Which enemy, or two calls can't be compared. When the first one dies, the next call is about someone else.
        enemy = min(fresh, key=lambda c: math.dist(c["pos"], [x, y]))
        ref = enemy["pos"]
        bearing = spoken_bearing(ref[0] - packet["pos"][0], ref[1] - packet["pos"][1], enemy.get("accuracy_m", 0))
        name = f"the enemy at {bearing}"
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
