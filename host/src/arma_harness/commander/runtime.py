"""The running commander: turns game events into radio traffic and wakes, and carries out its tool calls.

Only four event types are ever read from the game: cmd_tick, cmd_report, cmd_truth and killed. Truth and kills go
straight to files for review. Tool results reveal nothing about what happened to a unit: consequences arrive by radio, or don't.
"""
from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import asdict
from typing import Protocol

from . import map as map_mod
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
MAX_SCHEDULES = 20
MIN_REPEAT_S = 30
MARKER_KINDS = {"enemy", "friendly", "objective", "phase_line", "area", "danger", "hypothesis", "note"}
MARKER_CONFIDENCE = {"low", "medium", "high"}
NOTES_LIMIT = 1500
QUESTION_TOPICS = {"position", "task", "strength", "ammo", "contacts", "eta"}
ORDER_CODE = "_this call brmh_cmd_fnc_order"
DELETE_CODE = "_this call brmh_cmd_fnc_deleteStation"
KILL_CODE = "_this call brmh_cmd_fnc_killStation"
SHOW_CODE = "_this call brmh_cmd_fnc_show"
MIRROR_CODE = "_this call brmh_cmd_fnc_mirror"


class Game(Protocol):
    def events(self, since: int, wait: float) -> dict: ...
    def exec(self, code: str, args: list) -> dict: ...


class Runtime:
    def __init__(self, game: Game, scenario: Scenario, records: Records, deliver, world_size: float = 0,
                 clock=time.monotonic, buildings: list[dict] | None = None):
        self.game, self.scenario, self.records, self.deliver = game, scenario, records, deliver
        self.world_size = world_size
        self.buildings = buildings or []
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
        self.success_reason: str = saved.get("success_reason", "")
        self.next_id: dict[str, int] = saved.get("next_id", {})
        self.schedules: dict[str, dict] = saved.get("schedules", {})
        self.missed: dict[str, int] = saved.get("missed", {})
        self.checked: dict[str, float] = saved.get("checked", {})
        self.last_checkin: dict[str, str] = saved.get("last_checkin", {})
        self.markers: dict[str, dict] = saved.get("markers", {
            m["id"]: {"id": m["id"], "kind": m.get("kind", "note"), "at": m["at"], "label": m.get("label", ""),
                      "confidence": "", "sources": [], "expires": None, "t": None}
            for m in scenario.markers.values()})
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
        number = self.next_id.get(prefix, 1)
        self.next_id[prefix] = number + 1
        return f"{prefix}{number}" if prefix in "WSM" else f"{prefix}-{number:04d}"

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
        if kind == "killed":
            self._kill(event)
            return
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
        self.wake.timers, self.schedules, self.missed = {}, {}, {}
        self.wake.notice("The mission has restarted. All stations, orders and timers have been reset.")
        self.dirty = True

    def _packet(self, event: dict) -> None:
        callsign = event.get("callsign")
        if callsign not in self.scenario.stations:
            return
        packet = {key: event.get(key) for key in (
            "callsign", "pos", "grid", "dir", "speed", "alive", "wounded", "baseline", "leader", "rounds",
            "rounds_baseline", "behaviour", "combat_mode", "order", "unable", "leg", "legs", "clearing", "cleared",
            "placed", "contacts")}
        packet["t"] = float(event.get("t", 0))
        self.packets[callsign] = packet
        if self.t0 is None or self.ended:
            return
        tracker = self.trackers.setdefault(callsign, Tracker())
        for report in tracker.update(packet, self.routes.get(callsign), packet["t"], self.buildings):
            if report.checked:
                self.checked[report.checked] = packet["t"]
            self._say(callsign, report.text, report.precedence, report.grid, packet["t"])

    def _truth(self, event: dict) -> None:
        if self.t0 is None:
            return
        self.records.truth({"t": round(self.rel(float(event.get("t", 0))), 1), "groups": event.get("groups")})
        if not self.ended:
            self._judge(event.get("groups") or [])

    def _kill(self, event: dict) -> None:
        """For the after-action review only. It's written to its own file, and nothing the commander sees reads it."""
        if self.t0 is None:
            return
        self.records.kill({"t": round(self.rel(float(event.get("t", 0))), 1),
                           **{key: event.get(key) for key in ("victim", "side", "victimPos", "killer", "killerSide",
                                                              "weapon", "distance")}})

    def _judge(self, groups: list[dict]) -> None:
        """The harness alone decides how a battle ends. The commander only hears the result."""
        alive = {group.get("group"): group.get("alive", 0) for group in groups}
        success = self.scenario.success
        if self.scenario.failure.get("all_stations_lost") and all(
                alive.get(callsign, 1) == 0 for callsign in self.scenario.stations):
            self._end("All stations have been lost.")
            return
        if self.success_at is not None or not success:
            return
        if success.get("enemy_cleared"):
            enemies = self.scenario.enemies
            if enemies and all(alive.get(enemy["id"], 1) == 0 for enemy in enemies):
                self.success_reason = "Objective achieved: the enemy has been cleared."
        elif "station" in success:
            target, _ = parse_grid(success["of"], self.world_size)
            for group in groups:
                if group.get("group") == success["station"] and group.get("alive") and group.get("pos") \
                        and math.dist(group["pos"], target) <= success["within_m"]:
                    self.success_reason = f"Objective achieved: {success['station']} reached grid {success['of']}."
        if self.success_reason:
            # True position can get there seconds before the group reports arriving. Let its last words through.
            self.success_at = self.rel() + SUCCESS_GRACE_S

    def _end(self, reason: str) -> None:
        self.ended = reason
        self.wake.timers, self.schedules = {}, {}
        self._show(f"MISSION END: {reason}")
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
                self._end(self.success_reason)
            if not self.ended and rel >= self.scenario.time_limit_s:
                self._end("Time limit reached.")
            self._fire_schedules()
            wake = self.wake.poll(self.now())
            if wake is not None:
                self._deliver(wake)
            if self.dirty:
                self.save()

    def _scenario_event(self, event: dict) -> None:
        code = {"delete_station": DELETE_CODE, "kill_station": KILL_CODE}[event["action"]]
        self._game_exec(code, [event["station"]])
        self.records.operator_log(f"{format_time(self.rel())} scenario event: {event['action']} {event['station']}")
        self.records.append("radio_events", {"t": round(self.rel(), 1),
                                             "scenario_event": f"{event['action']} {event['station']}"})
        self.dirty = True

    def _game_exec(self, code: str, args: list) -> None:
        """Failures go to the operator's log only. The commander must see the same result either way."""
        try:
            result = self.game.exec(code, args)
            if not result.get("ok"):
                self.records.operator_log(f"exec failed: {code} {args} -> {result}")
        except Exception as exc:
            self.records.operator_log(f"exec failed: {code} {args} -> {exc}")

    # -- what a human observer sees in game, when the scenario has one. Nothing here reads anything back. -------

    def _show(self, text: str) -> None:
        if self.scenario.spectator:
            self._game_exec(SHOW_CODE, [text])

    def _mirror(self, marker: dict, removed: bool = False) -> None:
        if self.scenario.spectator:
            at = marker["at"] if isinstance(marker["at"], list) else [marker["at"]]
            points = [parse_grid(grid, self.world_size)[0] for grid in at]
            self._game_exec(MIRROR_CODE, [marker["id"], marker["kind"], points, marker.get("label", ""),
                                          marker.get("confidence", ""), removed])

    # -- radio ------------------------------------------------------------------------------------

    def _log_radio(self, sender: str, to: str, text: str, kind: str, precedence: str = reports.ROUTINE,
                   t: float | None = None) -> dict:
        row = {"id": self._id("R"), "t": round(self.rel(t), 1), "from": sender, "to": to, "text": text, "kind": kind,
               "precedence": precedence}
        self.radio.append(row)
        self.records.append("radio", row)
        self.dirty = True
        self._show(f"{sender}: {text}")
        return row

    def _heard(self, callsign: str, grid: str | None, t: float) -> None:
        self.last_heard[callsign] = t
        self.missed.pop(callsign, None)
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
        for timer in wake.timers:
            self._advance(self.schedules.get(timer["id"]))
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
        if self.missed:
            lines += ["", "OVERDUE"]
            for callsign, count in self.missed.items():
                checks = "check-in" if count == 1 else "check-ins"
                lines.append(f"{callsign}: missed {count} scheduled {checks}.")
        lines += ["", "NET"]
        for callsign in self.scenario.stations:
            heard = self.last_heard.get(callsign)
            when = f"last heard {_ago(self.now() - heard)}" if heard is not None else "not heard yet"
            lines.append(f"{callsign}  {when}")
        lines += self._map_lines()
        if self.checked:
            lines += ["", "BUILDINGS CHECKED"]
            lines += ["  ".join(f"{building} {_ago(self.now() - t).replace(' ago', '')}"
                                for building, t in sorted(self.checked.items(), key=lambda item: item[1]))]
        if self.schedules:
            lines += ["", "SCHEDULED"]
            for entry in sorted(self.schedules.values(), key=lambda e: e["due"]):
                repeat = f", every {_clock(entry['every'])}" if entry.get("every") else ""
                lines.append(f"{entry['id']}  {format_time(self.rel(entry['due']))}{repeat}  {entry['words']}")
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
        for marker in self.markers.values():
            lines.append(self._marker_line(marker))
        if len(lines) == 2:
            lines.append("Nothing plotted yet.")
        return lines

    def _marker_line(self, marker: dict) -> str:
        at = marker["at"]
        place = f"grids {'; '.join(at)}" if isinstance(at, list) else f"grid {at}"
        parts = [f"{marker['id']}  {marker['kind']} {marker.get('label', '')}".rstrip(), place]
        if marker.get("confidence"):
            parts.append(marker["confidence"])
        if marker.get("t") is not None:
            parts.append(_ago(self.rel() - marker["t"]).replace(" ago", " old"))
        if marker.get("expires") is not None and self.rel() >= marker["expires"]:
            parts.append("STALE")
        return "  ".join(parts)

    def save(self) -> None:
        self.records.save_state({
            "t0": self.t0, "turn": self.turn, "cursor": self.cursor, "delivered": self.delivered,
            "ended": self.ended, "success_at": self.success_at, "success_reason": self.success_reason,
            "next_id": self.next_id, "routes": self.routes, "schedules": self.schedules, "missed": self.missed,
            "markers": self.markers, "checked": self.checked, "last_checkin": self.last_checkin,
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
                self._show("The battle has started.")
                for marker in self.markers.values():
                    self._mirror(marker)
            self._used()
            self.save()
            return {
                "time": format_time(self.rel()), "mission": self.scenario.text,
                "time_limit": format_time(self.scenario.time_limit_s),
                "roster": self.roster()["stations"],
                "markers": [{"id": m["id"], "kind": m["kind"], "label": m.get("label"), "at": m["at"]}
                            for m in self.markers.values()],
                "buildings": [{"id": b["id"], "type": b["name"], "grid": b["at"], "positions": b["positions"]}
                              for b in self.buildings],
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
            order_id = self._send_order(request)
            self._used()
            self.save()
            return {"order": order_id, "sent": True}

    def _send_order(self, request: dict, via: str = "") -> str:
        checked = orders_mod.validate(request, self.scenario.stations, self.markers, self.world_size, self.buildings)
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
        suffix = f" (timed, {via})" if via else ""
        self._log_radio("HQ", callsign, f"{order_id}: {_order_words(request)}{suffix}", "order")
        self.records.append("orders", {"id": order_id, "t": round(self.rel(), 1), "request": request, "via": via})
        return order_id

    def _ask_targets(self, to, topics) -> list[str]:
        unknown = set(topics or []) - QUESTION_TOPICS
        if unknown:
            raise Invalid(f"Unknown topics {sorted(unknown)}: use {sorted(QUESTION_TOPICS)}.")
        if to == "all":
            return list(self.scenario.stations)
        if to in self.scenario.stations:
            return [to]
        raise Invalid(f"Unknown callsign {to!r}. See commander_roster.")

    def _reply_to(self, callsign: str, topics: list[str] | None) -> tuple[str | None, str | None]:
        """(words, grid they state) from the station's latest packet, or (None, None) if it can't answer."""
        packet = self.packets.get(callsign)
        if packet is None or self.now() - packet["t"] > PACKET_FRESH_S:
            return None, None
        grid = format_grid(packet["grid"]) if topics is None or "position" in topics else None
        return reports.answer(packet, self.routes.get(callsign), topics, self.buildings), grid

    def ask(self, to: str, topics: list[str] | None = None) -> dict:
        with self.lock:
            self._require_started()
            topics = topics or None
            targets = self._ask_targets(to, topics)
            wants = "SITREP" if not topics else ", ".join(topics)
            replies = []
            for callsign in targets:
                self._log_radio("HQ", callsign, f"Question: {wants}", "question")
                text, grid = self._reply_to(callsign, topics)
                if text is None:
                    self._log_radio(callsign, "HQ", "No answer.", "no_answer")
                    replies.append({"from": callsign, "text": "No answer."})
                    continue
                self._log_radio(callsign, "HQ", text, "reply")
                self._heard(callsign, grid, self.now())
                replies.append({"from": callsign, "text": text})
            self._used()
            self.save()
            return {"replies": replies}

    def schedule(self, do: dict, after=None, at=None, every=None, count=None, until=None) -> dict:
        """Wakes give the commander a turn. Timed orders and questions go out on time without one."""
        with self.lock:
            self._require_started()
            if (after is not None and at is not None) or (after is None and at is None and every is None):
                raise Invalid("Give after or at, or every. every can be combined with after for its first time.")
            kinds = [kind for kind in ("wake", "order", "ask") if isinstance(do, dict) and do.get(kind)]
            if len(kinds) != 1:
                raise Invalid('do needs one of: {"wake": "why"}, {"order": {...}} or {"ask": {"to": ...}}.')
            kind, what = kinds[0], do[kinds[0]]
            if len(self.schedules) >= MAX_SCHEDULES:
                raise Invalid(f"At most {MAX_SCHEDULES} schedules can be active.")
            interval = parse_time(every) if every is not None else None
            if interval is not None and interval < MIN_REPEAT_S:
                raise Invalid(f"Schedules can repeat at most every {_clock(MIN_REPEAT_S)}.")
            if at is not None:
                first = parse_time(at)
            else:
                first = self.rel() + (parse_time(after) if after is not None else interval)
            if first <= self.rel():
                raise Invalid(f"{format_time(first)} has already passed. It's {format_time(self.rel())}.")
            if kind == "wake" and not isinstance(what, str):
                raise Invalid('A wake needs a note: {"wake": "why you want to wake"}.')
            if kind == "order":
                orders_mod.validate(what, self.scenario.stations, self.markers, self.world_size, self.buildings)
            if kind == "ask":
                self._ask_targets(what.get("to"), what.get("topics"))
            base = self.t0 or 0.0
            entry = {"id": self._id("W" if kind == "wake" else "S"), "kind": kind, "what": what, "due": base + first,
                     "every": interval, "count": count, "until": base + parse_time(until) if until else None,
                     "words": _schedule_words(kind, what)}
            if kind == "wake":
                self.wake.add_timer(entry["id"], entry["due"], what.strip())
            self.schedules[entry["id"]] = entry
            self.records.append("schedule", {"id": entry["id"], "t": round(self.rel(), 1), "due": first, "kind": kind,
                                             "every": interval, "words": entry["words"]})
            self._used()
            self.save()
            return {"id": entry["id"], "first": format_time(first), "time_now": format_time(self.rel())}

    def _fire_schedules(self) -> None:
        now = self.now()
        for entry in sorted(self.schedules.values(), key=lambda e: e["due"]):
            if entry["kind"] == "wake" or entry["due"] > now:
                continue
            if entry["kind"] == "order":
                try:
                    self._send_order(entry["what"], entry["id"])
                except Invalid as exc:  # a marker it relied on has since been retired
                    self.records.operator_log(f"{entry['id']} couldn't fire: {exc}")
            else:
                self._timed_ask(entry)
            self._advance(entry)
            self.dirty = True

    def _timed_ask(self, entry: dict) -> None:
        topics = entry["what"].get("topics") or None
        wants = "SITREP" if not topics else ", ".join(topics)
        for callsign in self._ask_targets(entry["what"].get("to"), topics):
            self._log_radio("HQ", callsign, f"Question ({entry['id']}): {wants}", "question")
            text, grid = self._reply_to(callsign, topics)
            if text is None:
                # Silence wakes nobody: it waits in the next briefing, under OVERDUE.
                self._log_radio(callsign, "HQ", "No answer.", "no_answer")
                self.missed[callsign] = self.missed.get(callsign, 0) + 1
            elif self.last_checkin.get(f"{entry['id']}:{callsign}") == text:
                # Nothing has changed, so it isn't worth a turn: the check-in still counts as being heard.
                self._log_radio(callsign, "HQ", text, "checkin_unchanged")
                self._heard(callsign, grid, self.now())
            else:
                self.last_checkin[f"{entry['id']}:{callsign}"] = text
                self._say(callsign, text, reports.ROUTINE, grid, self.now())

    def _advance(self, entry: dict | None) -> None:
        """After a schedule fires: drop it, or set up its next time."""
        if entry is None:
            return
        if entry.get("count"):
            entry["count"] -= 1
        due = entry["due"] + (entry.get("every") or 0)
        finished = not entry.get("every") or entry.get("count") == 0 or (entry.get("until") and due > entry["until"])
        if finished:
            self.schedules.pop(entry["id"], None)
            return
        entry["due"] = due
        if entry["kind"] == "wake":
            self.wake.add_timer(entry["id"], due, entry["what"].strip())

    def unschedule(self, schedule_id: str) -> dict:
        with self.lock:
            existed = self.schedules.pop(schedule_id, None) is not None
            self.wake.cancel_timer(schedule_id)
            self.records.append("schedule", {"id": schedule_id, "t": round(self.rel(), 1), "cancelled": existed})
            self._used()
            self.save()
            return {"cancelled": existed}

    def mark(self, args: dict) -> dict:
        """Create or update a marker. The map holds belief: only the commander changes or retires it."""
        with self.lock:
            self._require_started()
            marker_id = args.get("id")
            if marker_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", str(marker_id)):
                raise Invalid("A marker id is up to 16 letters, digits, - or _.")
            if any(building["id"] == marker_id for building in self.buildings):
                raise Invalid(f"{marker_id} is a building's id. Choose another for this marker.")
            existing = self.markers.get(marker_id, {})
            if not existing and not args.get("at"):
                raise Invalid("A new marker needs at: a grid, or a list of grids for a line or area.")
            at = _marker_place(args["at"], self.world_size) if args.get("at") else existing["at"]
            kind = str(args.get("kind") or existing.get("kind") or "note").lower()
            if kind not in MARKER_KINDS:
                raise Invalid(f"Bad kind {kind!r}: use one of {', '.join(sorted(MARKER_KINDS))}.")
            confidence = str(args.get("confidence") or existing.get("confidence") or "").lower()
            if confidence and confidence not in MARKER_CONFIDENCE:
                raise Invalid(f"Bad confidence {confidence!r}: use low, medium or high.")
            expires = parse_time(args["expires"]) if args.get("expires") else existing.get("expires")
            marker = {"id": marker_id or self._id("M"), "kind": kind, "at": at,
                      "label": args.get("label", existing.get("label", "")), "confidence": confidence,
                      "sources": args.get("sources", existing.get("sources", [])), "expires": expires,
                      "t": round(self.rel(), 1)}
            self.markers[marker["id"]] = marker
            self.records.append("markers", marker)
            self._mirror(marker)
            self._used()
            self.save()
            return {"id": marker["id"], "time_now": format_time(self.rel())}

    def unmark(self, marker_id: str) -> dict:
        with self.lock:
            marker = self.markers.pop(marker_id, None)
            if marker is None:
                raise Invalid(f"No marker {marker_id!r}. Your markers are listed in every briefing.")
            self.records.append("markers", {"id": marker_id, "t": round(self.rel(), 1), "retired": True})
            self._mirror(marker, removed=True)
            self._used()
            self.save()
            return {"retired": marker_id}

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

    def map_image(self, center=None, radius=None) -> dict:
        """The commander's map as a picture: what it has been told, and nothing else."""
        with self.lock:
            self._require_started()
            ao = self.scenario.ao
            if center:
                known = {building["id"]: building for building in self.buildings}
                place, _ = orders_mod.resolve_place(center, {**self.markers, **known}, self.world_size)
            elif ao:
                place = parse_grid(ao["at"], self.world_size)[0]
            else:
                place = [self.world_size / 2, self.world_size / 2]
            size = float(radius or (ao or {}).get("radius", 500))
            if not 50 <= size <= 5000:
                raise Invalid("radius must be between 50 and 5000 metres.")
            positions = {callsign: {"grid": place_["grid"], "age": _ago(self.now() - place_["t"])}
                         for callsign, place_ in self.positions.items()}
            caption = (f"{format_time(self.rel())}. Your beliefs and last reports, not live. Green: buildings checked. "
                       f"Grid lines every {100 if size <= 800 else 500 if size <= 3000 else 1000} m.")
            png = map_mod.render(place, size, self.buildings, list(self.markers.values()), positions, self.checked,
                                 caption)
            self._used()
            return {"png": png, "text": caption}

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


def _clock(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _marker_place(at, world_size: float):
    """A grid in its spoken form, or a list of them for a line or area."""
    if isinstance(at, list):
        if len(at) < 2:
            raise Invalid("A line or area needs at least 2 grids.")
        return [parse_grid(grid, world_size)[1] for grid in at]
    return parse_grid(at, world_size)[1]


def _schedule_words(kind: str, what) -> str:
    if kind == "wake":
        return f'wake: "{what}"'
    if kind == "order":
        return f"{what.get('to')}: {_order_words(what)}"
    topics = ", ".join(what.get("topics") or []) or "SITREP"
    return f"{what.get('to')}: {topics}"


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
