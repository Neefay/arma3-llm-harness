"""The running commander: turns game events into radio traffic and wakes, and carries out its tool calls.

Only three event types are ever read from the game: cmd_tick, cmd_report and cmd_truth. Truth goes straight
to a file. Tool results reveal nothing about what happened to a unit: consequences arrive by radio, or don't.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import asdict
from typing import Protocol

from . import orders as orders_mod
from . import reports
from .orders import Invalid, format_time, parse_grid, parse_time
from .records import Records
from .reports import Tracker, format_grid
from .scenario import Scenario
from .wake import Wake, WakeLogic

PACKET_FRESH_S = 6
CLOCK_COAST_S = 3
GAME_LOST_S = 15
SUCCESS_GRACE_S = 10
TRAFFIC_CAP = 25
MAX_WAKES = 20
NOTES_LIMIT = 1500
QUESTION_TOPICS = {"position", "task", "strength", "ammo", "contacts", "eta"}
ORDER_CODE = "_this call brmh_cmd_fnc_order"
DELETE_CODE = "_this call brmh_cmd_fnc_deleteStation"


class Game(Protocol):
    def events(self, since: int, wait: float) -> dict: ...
    def exec(self, code: str, args: list) -> dict: ...


class Runtime:
    def __init__(self, game: Game, scenario: Scenario, records: Records, deliver, world_size: float = 0,
                 clock=time.monotonic):
        self.game, self.scenario, self.records, self.deliver = game, scenario, records, deliver
        self.world_size = world_size
        self.wall = clock
        self.lock = threading.RLock()
        self.mission_t: float | None = None
        self.seen_at = 0.0
        self.packets: dict[str, dict] = {}
        self.game_lost_since: float | None = None
        self.game_lost_said = False
        self.dirty = False

        saved = records.load_state()
        self.t0: float | None = saved.get("t0")
        self.turn: int = saved.get("turn", 0)
        self.cursor: int | None = saved.get("cursor")
        self.delivered: int = saved.get("delivered", 0)
        self.ended: str = saved.get("ended", "")
        self.success_at: float | None = saved.get("success_at")
        self.next_id: dict[str, int] = saved.get("next_id", {"R": 1, "O": 1, "W": 1})
        self.routes: dict[str, dict] = saved.get("routes", {})
        self.last_heard: dict[str, float] = saved.get("last_heard", {})
        self.positions: dict[str, dict] = saved.get("positions", {})
        self.events_done: list[int] = saved.get("events_done", [])
        self.turn_row: dict | None = saved.get("turn_row")
        self.trackers = {k: Tracker(**v) for k, v in saved.get("trackers", {}).items()}
        if "wake" in saved:
            self.wake = WakeLogic(**saved["wake"])
        else:
            self.wake = WakeLogic(quiet_s=scenario.quiet_s, ceiling_s=scenario.ceiling_s,
                                  mode=scenario.mid_turn_messages)
        self.radio: list[dict] = records.read("radio")

    # -- clock -----------------------------------------------------------------------------------

    def now(self) -> float:
        """Mission time. It coasts briefly between ticks, and stops if ticks stop, as when the game is paused."""
        if self.mission_t is None:
            return 0.0
        return self.mission_t + min(self.wall() - self.seen_at, CLOCK_COAST_S)

    def rel(self, t: float | None = None) -> float:
        return (self.now() if t is None else t) - (self.t0 or 0.0)

    def _id(self, prefix: str) -> str:
        number = self.next_id[prefix]
        self.next_id[prefix] = number + 1
        return f"{prefix}{number}" if prefix == "W" else f"{prefix}-{number:04d}"

    # -- game side -------------------------------------------------------------------------------

    def step(self, wait: float = 0.5) -> None:
        """One pass of the background loop: read events, run scenario events, deliver any wake due."""
        try:
            if self.cursor is None:
                self.cursor = int(self.game.events(1 << 60, 0).get("next", 0))
            result = self.game.events(self.cursor, wait)
        except Exception as exc:  # any failure here means the game is out of reach
            self._game_lost(exc)
            return
        with self.lock:
            self.game_lost_since, self.game_lost_said = None, False
            for event in result.get("events", []):
                self._event(event)
            self.cursor = result.get("next", self.cursor)
            self.tick()

    def _game_lost(self, exc: Exception) -> None:
        with self.lock:
            if self.game_lost_since is None:
                self.game_lost_since = self.wall()
                self.records.operator_log(f"game unreachable: {exc}")
            if self.t0 is not None and not self.ended and not self.game_lost_said \
                    and self.wall() - self.game_lost_since >= GAME_LOST_S:
                self.game_lost_said = True
                self.wake.notice("System fault: the connection to the battle has been lost. This is not a battle "
                                 "event. Nothing can be reported or ordered until it returns.")
                self.tick()

    def _event(self, event: dict) -> None:
        if event.get("k") == "mission" and event.get("state") == "start" and self.t0 is not None:
            self._mission_restarted()
            return
        if event.get("k") != "evt":
            return
        kind = event.get("type")
        if kind not in ("cmd_tick", "cmd_report", "cmd_truth"):
            return
        self.mission_t, self.seen_at = float(event.get("t", 0)), self.wall()
        if kind == "cmd_report":
            self._packet(event)
        elif kind == "cmd_truth":
            self._truth(event)
        self.dirty = True

    def _mission_restarted(self) -> None:
        self.routes, self.trackers, self.packets = {}, {}, {}
        self.wake.timers = {}
        self.wake.notice("The mission has restarted. All stations, orders and timers have been reset.")
        self.dirty = True

    def _packet(self, event: dict) -> None:
        callsign = event.get("callsign")
        if callsign not in self.scenario.stations:
            return
        packet = {key: event.get(key) for key in (
            "callsign", "pos", "grid", "dir", "speed", "alive", "wounded", "baseline", "leader", "rounds",
            "rounds_baseline", "behaviour", "combat_mode", "order", "unable", "leg", "legs", "contacts")}
        packet["t"] = float(event.get("t", 0))
        self.packets[callsign] = packet
        if self.t0 is None or self.ended:
            return
        tracker = self.trackers.setdefault(callsign, Tracker())
        for report in tracker.update(packet, self.routes.get(callsign), packet["t"]):
            self._say(callsign, report.text, report.precedence, report.grid, packet["t"])

    def _truth(self, event: dict) -> None:
        if self.t0 is None:
            return
        self.records.truth({"t": round(self.rel(float(event.get("t", 0))), 1), "groups": event.get("groups")})
        self._check_success(event.get("groups") or [])

    def _check_success(self, groups: list[dict]) -> None:
        success = self.scenario.success
        if not success or self.ended:
            return
        target, _ = parse_grid(success["of"], self.world_size)
        for group in groups:
            if self.success_at is None and group.get("group") == success["station"] and group.get("alive") \
                    and group.get("pos") and math.dist(group["pos"], target) <= success["within_m"]:
                # True position can get there seconds before the group reports arriving. Let its last words through.
                self.success_at = self.rel() + SUCCESS_GRACE_S

    def _end(self, reason: str) -> None:
        self.ended = reason
        self.wake.timers = {}
        self.wake.notice(f"MISSION END. {reason} No further orders are needed. End your turn.")
        self.records.append("radio_events", {"t": round(self.rel(), 1), "mission_end": reason})
        self.dirty = True

    def tick(self) -> None:
        """Scenario events, the time limit, and any wake due. Nothing runs until the mission has started."""
        with self.lock:
            if self.t0 is None:
                return
            rel = self.rel()
            for index, event in enumerate(self.scenario.events):
                if index not in self.events_done and rel >= event["at_s"]:
                    self.events_done.append(index)
                    self._scenario_event(event)
            if not self.ended and self.success_at is not None and rel >= self.success_at:
                success = self.scenario.success
                self._end(f"Objective achieved: {success['station']} reached grid {success['of']}.")
            if not self.ended and rel >= self.scenario.time_limit_s:
                self._end("Time limit reached.")
            wake = self.wake.poll(self.now())
            if wake is not None:
                self._deliver(wake)
            if self.dirty:
                self.save()

    def _scenario_event(self, event: dict) -> None:
        if event.get("action") == "delete_station":
            self._game_exec(DELETE_CODE, [event["station"]])
            self.records.operator_log(f"{format_time(self.rel())} scenario event: deleted {event['station']}")
        self.dirty = True

    def _game_exec(self, code: str, args: list) -> None:
        """Failures go to the operator's log only. The commander must see the same result either way."""
        try:
            result = self.game.exec(code, args)
            if not result.get("ok"):
                self.records.operator_log(f"exec failed: {code} {args} -> {result}")
        except Exception as exc:
            self.records.operator_log(f"exec failed: {code} {args} -> {exc}")

    # -- radio ------------------------------------------------------------------------------------

    def _log_radio(self, sender: str, to: str, text: str, kind: str, precedence: str = reports.ROUTINE,
                   t: float | None = None) -> dict:
        row = {"id": self._id("R"), "t": round(self.rel(t), 1), "from": sender, "to": to, "text": text, "kind": kind,
               "precedence": precedence}
        self.radio.append(row)
        self.records.append("radio", row)
        self.dirty = True
        return row

    def _heard(self, callsign: str, grid: str | None, t: float) -> None:
        self.last_heard[callsign] = t
        if grid:
            self.positions[callsign] = {"grid": grid, "t": t}

    def _say(self, callsign: str, text: str, precedence: str, grid: str | None, t: float) -> None:
        self._log_radio(callsign, "HQ", text, "report", precedence, t)
        self._heard(callsign, grid, t)
        self.wake.message(t)

    # -- turns and briefings -----------------------------------------------------------------------

    def _deliver(self, wake: Wake) -> None:
        if wake.fallback:
            self._close_turn("assumed over: no end-turn call")
        else:
            self._close_turn("interrupted: a wake was delivered during this turn")
        self.turn += 1
        text = self.briefing(wake)
        self.delivered = len(self.radio)
        self.turn_row = {"turn": self.turn, "start": round(self.rel(), 1), "mode": self.wake.mode,
                         "woke_on": wake.reason(), "messages": wake.messages, "timers": [t["id"] for t in wake.timers]}
        self.dirty = True
        self.deliver(text, {"turn": str(self.turn), "woke_on": wake.reason()})

    def _close_turn(self, note: str) -> None:
        if self.turn_row is None:
            return
        row = {**self.turn_row, "end": round(self.rel(), 1), "note": note}
        row["duration"] = round(row["end"] - row["start"], 1)
        self.records.append("turns", row)
        self.turn_row = None

    def briefing(self, wake: Wake | None = None) -> str:
        reason = wake.reason() if wake else "request"
        lines = [f"{format_time(self.rel())} | turn {self.turn} | woke on: {reason}"]
        if wake and wake.notices:
            lines += ["", "NOTICE", *wake.notices]
        if wake and wake.timers:
            lines += ["", "TIMERS DUE"]
            for timer in wake.timers:
                late = self.now() - timer["due"]
                delay = f", delivered {round(late)} s late" if late >= 1 else ""
                lines.append(f"{timer['id']}  due {format_time(self.rel(timer['due']))}{delay}: \"{timer['note']}\"")
        traffic = self._traffic()
        if traffic:
            lines += ["", "TRAFFIC", *traffic]
        lines += ["", "NET"]
        for callsign in self.scenario.stations:
            heard = self.last_heard.get(callsign)
            when = f"last heard {_ago(self.now() - heard)}" if heard is not None else "not heard yet"
            lines.append(f"{callsign}  {when}")
        lines += self._map_lines()
        if self.wake.timers:
            lines += ["", "SCHEDULED"]
            for timer in sorted(self.wake.timers.values(), key=lambda t: t["due"]):
                lines.append(f"{timer['id']}  {format_time(self.rel(timer['due']))}  wake: \"{timer['note']}\"")
        notes = self.records.notes()
        if notes:
            lines += ["", "YOUR NOTES", notes]
        return "\n".join(lines)

    def _traffic(self) -> list[str]:
        rows = [r for r in self.radio[self.delivered:] if r["kind"] == "report"]
        hidden = 0
        if len(rows) > TRAFFIC_CAP:
            urgent = [r for r in rows if r["precedence"] != reports.ROUTINE]
            room = max(0, TRAFFIC_CAP - len(urgent))
            routine = [r for r in rows if r["precedence"] == reports.ROUTINE]
            kept = {r["id"] for r in urgent + (routine[-room:] if room else [])}
            hidden = len(rows) - len(kept)
            rows = [r for r in rows if r["id"] in kept]
        lines = [_radio_line(r) for r in rows]
        if hidden:
            lines.insert(0, f"(+{hidden} earlier routine messages: see commander_log)")
        return lines

    def _map_lines(self) -> list[str]:
        lines = ["", "YOUR MAP"]
        for callsign, place in self.positions.items():
            lines.append(f"{callsign}  grid {place['grid']}  reported {_ago(self.now() - place['t'])}")
        for marker in self.scenario.markers.values():
            lines.append(f"{marker['id']}  {marker.get('kind', 'note')} {marker.get('label', '')}  grid {marker['at']}")
        if len(lines) == 2:
            lines.append("Nothing plotted yet.")
        return lines

    def save(self) -> None:
        self.records.save_state({
            "t0": self.t0, "turn": self.turn, "cursor": self.cursor, "delivered": self.delivered,
            "ended": self.ended, "success_at": self.success_at, "next_id": self.next_id, "routes": self.routes,
            "last_heard": self.last_heard,
            "positions": self.positions, "events_done": self.events_done, "turn_row": self.turn_row,
            "trackers": {k: asdict(v) for k, v in self.trackers.items()}, "wake": asdict(self.wake),
        })
        self.dirty = False

    # -- tools -----------------------------------------------------------------------------------

    def _used(self) -> None:
        self.wake.tool_used(self.now())
        self.dirty = True

    def mission(self) -> dict:
        """Starts the mission clock on the first call: until then, the battle hasn't begun for the commander."""
        with self.lock:
            if self.mission_t is None:
                return {"ready": False, "text": "The net isn't up yet. Call commander_mission again in a few seconds."}
            if self.t0 is None:
                self.t0 = self.now()
                self.turn = 1
                self.delivered = len(self.radio)
                self.turn_row = {"turn": 1, "start": 0.0, "mode": self.wake.mode, "woke_on": "mission start",
                                 "messages": 0, "timers": []}
                self.wake.turn_started(self.now())
                for callsign in self.scenario.stations:
                    self.last_heard.setdefault(callsign, self.now())
            self._used()
            self.save()
            return {
                "time": format_time(self.rel()), "mission": self.scenario.text,
                "time_limit": format_time(self.scenario.time_limit_s),
                "roster": self.roster()["stations"],
                "markers": [{"id": m["id"], "kind": m.get("kind"), "label": m.get("label"), "grid": m["at"]}
                            for m in self.scenario.markers.values()],
                "ended": self.ended or None,
            }

    def roster(self) -> dict:
        with self.lock:
            stations = []
            for station in self.scenario.stations.values():
                heard = self.last_heard.get(station["callsign"])
                stations.append({"callsign": station["callsign"], "role": station["role"],
                                 "capabilities": station["capabilities"],
                                 "last_heard": _ago(self.now() - heard) if heard is not None else "not yet"})
            return {"stations": stations}

    def order(self, request: dict) -> dict:
        with self.lock:
            self._require_started()
            checked = orders_mod.validate(request, self.scenario.stations, self.scenario.markers, self.world_size)
            order_id = self._id("O")
            callsign = checked["to"]
            previous = self.routes.get(callsign)
            mode, route = checked["mode"], checked["route"]
            if mode == "posture":
                base = previous or {"kind": "posture", "legs": []}
                route = {**base, "keeps_progress": order_id, "acknowledge": "Copy."}
            elif mode == "append" and previous and previous.get("kind") == "route":
                words = reports.leg_words(route["legs"])
                route = {"kind": "route", "legs": previous["legs"] + route["legs"], "keeps_progress": order_id,
                         "acknowledge": f"Copy, then {words}."}
            elif mode == "append":
                mode = "replace"
            self.routes[callsign] = route
            self._game_exec(ORDER_CODE, [callsign, order_id, mode, checked["engine_legs"], checked["posture"]])
            text = f"{order_id}: {_order_words(request)}"
            self._log_radio("HQ", callsign, text, "order")
            self.records.append("orders", {"id": order_id, "t": round(self.rel(), 1), "request": request})
            self._used()
            self.save()
            return {"order": order_id, "sent": True}

    def ask(self, to: str, topics: list[str] | None = None) -> dict:
        with self.lock:
            self._require_started()
            if to == "all":
                targets = list(self.scenario.stations)
            elif to in self.scenario.stations:
                targets = [to]
            else:
                raise Invalid(f"Unknown callsign {to!r}. See commander_roster.")
            topics = topics or None
            unknown = set(topics or []) - QUESTION_TOPICS
            if unknown:
                raise Invalid(f"Unknown topics {sorted(unknown)}: use {sorted(QUESTION_TOPICS)}.")
            wants = "SITREP" if not topics else ", ".join(topics)
            replies = []
            for callsign in targets:
                self._log_radio("HQ", callsign, f"Question: {wants}", "question")
                packet = self.packets.get(callsign)
                if packet is None or self.now() - packet["t"] > PACKET_FRESH_S:
                    self._log_radio(callsign, "HQ", "No answer.", "no_answer")
                    replies.append({"from": callsign, "text": "No answer."})
                    continue
                text = reports.answer(packet, self.routes.get(callsign), topics)
                self._log_radio(callsign, "HQ", text, "reply")
                has_position = topics is None or "position" in topics
                self._heard(callsign, format_grid(packet["grid"]) if has_position else None, self.now())
                replies.append({"from": callsign, "text": text})
            self._used()
            self.save()
            return {"replies": replies}

    def schedule(self, do: dict, after=None, at=None) -> dict:
        with self.lock:
            self._require_started()
            if (after is None) == (at is None):
                raise Invalid("Give exactly one of after or at.")
            note = do.get("wake") if isinstance(do, dict) else None
            if not isinstance(note, str) or not note.strip():
                raise Invalid('Only wake schedules are available so far: do={"wake": "why you want to wake"}.')
            if len(self.wake.timers) >= MAX_WAKES:
                raise Invalid(f"At most {MAX_WAKES} wakes can be active.")
            rel_due = self.rel() + parse_time(after) if after is not None else parse_time(at)
            if rel_due <= self.rel():
                raise Invalid(f"{format_time(rel_due)} has already passed. It's {format_time(self.rel())}.")
            timer_id = self._id("W")
            self.wake.add_timer(timer_id, (self.t0 or 0.0) + rel_due, note.strip())
            self.records.append("schedule", {"id": timer_id, "t": round(self.rel(), 1), "due": rel_due, "note": note})
            self._used()
            self.save()
            return {"id": timer_id, "wakes_at": format_time(rel_due)}

    def unschedule(self, timer_id: str) -> dict:
        with self.lock:
            cancelled = self.wake.cancel_timer(timer_id)
            self.records.append("schedule", {"id": timer_id, "t": round(self.rel(), 1), "cancelled": cancelled})
            self._used()
            self.save()
            return {"cancelled": cancelled}

    def end_turn(self, note: str = "", messages_only: bool = False) -> dict:
        with self.lock:
            self._require_started()
            if not self.ended and not self.wake.can_end_turn(messages_only):
                return {"ended": False, "error": "No wake is scheduled. Set one with commander_schedule, or pass "
                                                 "messages_only=true to wait only for incoming messages."}
            self.wake.end_turn(messages_only)
            self._close_turn(note)
            self.dirty = True
            self.save()
            return {"ended": True, "mission_over": bool(self.ended)}

    def brief(self) -> dict:
        with self.lock:
            self._used()
            return {"briefing": self.briefing()}

    def notes(self, text: str) -> dict:
        with self.lock:
            if len(text) > NOTES_LIMIT:
                raise Invalid(f"Notes are limited to {NOTES_LIMIT} characters. These are {len(text)}.")
            self.records.set_notes(text)
            self._used()
            return {"saved": True}

    def log(self, since=None, sender: str | None = None, limit: int = 50) -> dict:
        with self.lock:
            start = parse_time(since) if since else 0
            rows = [r for r in self.radio if r["t"] >= start and (not sender or r["from"] == sender)]
            self._used()
            return {"log": [_radio_line(r) for r in rows[-max(1, int(limit)):]]}

    def _require_started(self) -> None:
        if self.t0 is None:
            raise Invalid("Call commander_mission first.")


def _ago(seconds: float) -> str:
    seconds = max(0, round(seconds))
    return f"{seconds} s ago" if seconds < 120 else f"{round(seconds / 60)} min ago"


def _radio_line(row: dict) -> str:
    flash = "FLASH " if row["precedence"] == reports.FLASH else ""
    stamp = format_time(row["t"])[2:]
    return f"[{stamp}] {flash}{row['from']}: {row['text']}"


def _order_words(request: dict) -> str:
    legs = ", ".join(f"{leg.get('type')} {leg.get('at', '')}".strip() for leg in request.get("legs") or []
                     if isinstance(leg, dict))
    return legs or "order"
