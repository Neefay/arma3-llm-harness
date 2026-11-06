"""The commander's MCP server: its entire interface to the world, plus the channel that wakes it.

Plain JSON-RPC over stdio, because channels need an experimental capability and a custom notification.
Keep TOOLS the complete list: a test fails if anything else appears. Errors here never carry engine details.
"""
from __future__ import annotations

import base64
import contextlib
import json
import sys
import threading
import time
import traceback
from importlib import resources

from .operator import load_current
from .orders import Invalid

# Delivered by the server, not as a CLAUDE.md: the tool lockdown denies Read, which also stops the client loading one.
DOCTRINE = resources.files("arma_harness.commander").joinpath("doctrine.md").read_text(encoding="utf-8")

ORDER_TYPES_HELP = (
    "MOVE. HOLD: go there and stay. SEARCH: fight what's noticed in an area, without entering buildings. CLEAR: go "
    "through the given buildings position by position. OCCUPY: move into a building and hold it. CORDON: spread out in "
    "a ring around a place, radius default 30 m, and watch it. ATTACK: slow combat advance on a place. DEFEND: "
    "garrison buildings around a place and hold. PATROL_AREA: patrol randomly around a place. SWEEP: search randomly, "
    "including some buildings, until replaced. SENTRY: wait at a place until enemies appear, then continue. PATROL: "
    "repeat a route. HALT. POSTURE: change settings only. MOUNT: get into a vehicle from your list, one man if you "
    "name a seat, or everyone who fits. DISMOUNT: get off one, or all of them. FIRE_MISSION: fire this station's "
    "crewed guns at a grid reference of six or eight figures, and only that: markers and building ids can't be called "
    "in. CHECK_FIRE: stop firing, though rounds in the air still land. Fire orders leave the squad's other orders as "
    "they are. CARRY: free men pick up casualties and take them to a vehicle or a place. UNLOAD: get casualties off a "
    "stopped vehicle. TREAT: medics treat casualties where they lie, faster at an aid post or medical vehicle. "
    "AID_POST: a medic sets up an aid post. These four leave the rest of the squad's orders as they are. The last six of the "
    "single-place orders run until replaced. Each stands alone in an order, except MOVE, "
    "HOLD, SEARCH and SENTRY, which can be chained.")
_STRING = {"type": "string"}
_LEG = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "description": ORDER_TYPES_HELP},
        "at": {"description": "Grid such as '034 030', a marker id, or a building id such as 'B3'. For PATROL, a "
                              "list of them. For CLEAR, a list of building ids, or a place plus radius. Needed by "
                              "every type except HALT and POSTURE, though HOLD or SENTRY after another leg can omit "
                              "it to stay where that leg ended."},
        "vehicle": {"type": "string", "description": "For MOUNT, DISMOUNT, CARRY and UNLOAD: an id from your list, "
                                                     "such as V1"},
        "casualties": {"type": "array", "items": _STRING,
                       "description": "For CARRY, UNLOAD and TREAT: ids from your list, such as C1. "
                                      "Default: all nearby"},
        "seat": {"type": "string", "description": "For MOUNT: driver, gunner, commander, cargo or turret:0"},
        "ammo": {"type": "string", "description": "For FIRE_MISSION: HE (default) or SMOKE"},
        "rounds": {"type": "integer", "description": "For FIRE_MISSION: rounds per gun, default 3"},
        "observer": {"type": "string",
                     "description": "For FIRE_MISSION: a station that corrects fire, to watch the fall of shot"},
        "guns": {"type": "array", "items": _STRING, "description": "For fire orders: which guns, default all crewed"},
        "radius": {"type": "number", "description": "Metres around the point"},
        "completion": {"type": "number", "description": "How close counts as arrived, in metres"},
        "hold_for": {"type": "string", "description": "Time to wait at the point, such as 1:30"},
    },
    "required": ["type"],
}

TOOLS = [
    {"name": "commander_mission", "description": "The mission brief, roster and markers. Call first: this starts the "
     "mission clock.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "commander_roster", "description": "Callsigns, roles, what each can do, and when each was last heard. "
     "It holds no live strength or status.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "commander_order", "description": "Send an order to one station. The result only confirms it was sent: "
     "watch the radio for an acknowledgement.", "inputSchema": {"type": "object", "properties": {
        "to": _STRING, "legs": {"type": "array", "items": _LEG},
        "mode": {"type": "string", "description": "replace (default) or append"},
        "speed": {"type": "string", "description": "LIMITED, NORMAL or FULL"},
        "formation": {"type": "string", "description": "COLUMN, STAG COLUMN, WEDGE, ECH LEFT, ECH RIGHT, VEE, LINE, "
                                                       "FILE or DIAMOND"},
        "behaviour": {"type": "string", "description": "CARELESS, SAFE, AWARE, COMBAT or STEALTH"},
        "combat_mode": {"type": "string", "description": "BLUE never fire, GREEN hold fire and keep formation, WHITE "
                                                         "hold fire and engage at will, YELLOW fire at will and keep "
                                                         "formation, RED fire at will and engage at will"},
        "intent": {"type": "string", "description": "Your purpose. Recorded for review"},
     }, "required": ["to", "legs"]}},
    {"name": "commander_ask", "description": "Ask a station for a full SITREP (no topics) or specific facts. Silence "
     "comes back as No answer. A squad in a fight says Wait one, and answers by message when it can. It only gives its "
     "own grid in a fight if you ask for position.", "inputSchema": {"type": "object", "properties": {
        "to": {"type": "string", "description": "A callsign, or all"},
        "topics": {"type": "array", "items": _STRING,
                   "description": "position, task, strength, ammo, contacts, eta or vehicles"},
     }, "required": ["to"]}},
    {"name": "commander_schedule", "description": "Do something later. When: after (such as 1:30), at (such as "
     "T+15:45) or every (such as 5:00, with optional count or until). What: do={'wake': 'why you want to wake'}, or "
     "do={'order': {same fields as commander_order}}, or do={'ask': {'to': ..., 'topics': [...]}}. Timed orders and "
     "questions go out on time without waking you, even during a turn. Replies wake you. Silence shows as OVERDUE in "
     "your next briefing.", "inputSchema": {
        "type": "object", "properties": {"after": _STRING, "at": _STRING, "every": _STRING,
                                         "count": {"type": "number"}, "until": _STRING, "do": {"type": "object"}},
        "required": ["do"]}},
    {"name": "commander_unschedule", "description": "Cancel a schedule by its id.", "inputSchema": {
        "type": "object", "properties": {"id": _STRING}, "required": ["id"]}},
    {"name": "commander_mark", "description": "Create or update a marker on your map: what you believe, not what's "
     "confirmed. Omit id to create one, reuse an id to update it. Markers appear in every briefing with their age, and "
     "orders can use a marker id instead of a grid.", "inputSchema": {"type": "object", "properties": {
        "id": _STRING, "kind": {"type": "string", "description": "enemy, friendly, objective, phase_line, area, "
                                                                 "danger, hypothesis or note"},
        "at": {"description": "A grid such as '034 030', a building id such as 'B3' to pin the marker to that "
                              "building, or a list of grids or building ids for a line or area"}, "label": _STRING,
        "confidence": {"type": "string", "description": "low, medium or high"},
        "sources": {"type": "array", "items": _STRING, "description": "Radio message ids behind this belief"},
        "expires": {"type": "string", "description": "Flag it as stale after this time, such as T+25:00"},
     }}},
    {"name": "commander_unmark", "description": "Retire a marker that no longer holds. Its history is kept for "
     "review.", "inputSchema": {"type": "object", "properties": {"id": _STRING}, "required": ["id"]}},
    {"name": "commander_end_turn", "description": "End your turn, with a short note. Refused when no wake is set, "
     "unless messages_only is true, which means you'll wake only for incoming messages.", "inputSchema": {
        "type": "object", "properties": {"note": _STRING, "messages_only": {"type": "boolean"}}}},
    {"name": "commander_map", "description": "A picture of your map: buildings with their ids, your markers and each "
     "station's last reported position. It shows your beliefs and last reports, not the live battle. Use it for "
     "geometry, such as routes and cordons. Your markers are already listed in every briefing as text.",
     "inputSchema": {
        "type": "object", "properties": {"center": {"type": "string", "description": "Grid, marker or building id. "
                                                                                    "Default: the whole area"},
                                         "radius": {"type": "number", "description": "Metres, 50 to 5000"}}}},
    {"name": "commander_brief", "description": "The current briefing, for catching up after losing track or resuming "
     "a session.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "commander_notes", "description": "Replace your notes, included in every briefing. Keep your plan and "
     "main worries here: it's how you remember them.", "inputSchema": {
        "type": "object", "properties": {"text": _STRING}, "required": ["text"]}},
    {"name": "commander_log", "description": "Earlier radio traffic, optionally since a time or from one station.",
     "inputSchema": {"type": "object", "properties": {"since": _STRING, "from": _STRING,
                                                      "limit": {"type": "number"}}}},
]
TOOL_NAMES = {tool["name"] for tool in TOOLS}


class Server:
    def __init__(self, stdin=None, stdout=None, runtime_factory=load_current):
        self.stdin = stdin or sys.stdin.buffer
        self.stdout = stdout or sys.stdout.buffer
        self.write_lock = threading.Lock()
        self.runtime_factory = runtime_factory
        self.runtime = None
        self.stop = threading.Event()

    def send(self, message: dict) -> None:
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self.write_lock:
            self.stdout.write(data)
            self.stdout.flush()

    def wake(self, text: str, meta: dict) -> None:
        self.send({"jsonrpc": "2.0", "method": "notifications/claude/channel",
                   "params": {"content": text, "meta": meta}})

    def get_runtime(self):
        if self.runtime is None:
            self.runtime = self.runtime_factory(self.wake)
            threading.Thread(target=self._loop, daemon=True).start()
        return self.runtime

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                self.runtime.step()
            except Exception:
                with contextlib.suppress(Exception):
                    self.runtime.records.operator_log(traceback.format_exc())
                time.sleep(1)

    def call(self, name: str, args: dict):
        if name not in TOOL_NAMES:
            raise Invalid(f"Unknown tool {name}.")
        runtime = self.get_runtime()
        match name:
            case "commander_mission":
                return {**runtime.mission(), "doctrine": DOCTRINE}
            case "commander_roster":
                return runtime.roster()
            case "commander_order":
                return runtime.order(args)
            case "commander_ask":
                return runtime.ask(args.get("to", ""), args.get("topics"))
            case "commander_schedule":
                return runtime.schedule(args.get("do"), args.get("after"), args.get("at"), args.get("every"),
                                        args.get("count"), args.get("until"))
            case "commander_map":
                return runtime.map_image(args.get("center"), args.get("radius"))
            case "commander_mark":
                return runtime.mark(args)
            case "commander_unmark":
                return runtime.unmark(args.get("id", ""))
            case "commander_unschedule":
                return runtime.unschedule(args.get("id", ""))
            case "commander_end_turn":
                return runtime.end_turn(args.get("note", ""), bool(args.get("messages_only")))
            case "commander_brief":
                return runtime.brief()
            case "commander_notes":
                return runtime.notes(args.get("text", ""))
            case "commander_log":
                return runtime.log(args.get("since"), args.get("from"), args.get("limit", 50))

    def _tool(self, request: dict) -> None:
        params = request.get("params") or {}
        name = params.get("name", "")
        is_error = False
        try:
            result = self.call(name, params.get("arguments") or {})
            if name == "commander_map":
                content = [{"type": "image", "data": base64.b64encode(result["png"]).decode(), "mimeType": "image/png"},
                           {"type": "text", "text": result["text"]}]
                self.send({"jsonrpc": "2.0", "id": request["id"], "result": {"content": content, "isError": False}})
                return
            text = result.get("briefing") if name == "commander_brief" else json.dumps(result, ensure_ascii=False)
        except Invalid as exc:
            text, is_error = str(exc), True
        except Exception:
            # Details go to the operator's log: an engine error could reveal what's happening in the game.
            with contextlib.suppress(Exception):
                self.runtime.records.operator_log(f"{name} failed:\n{traceback.format_exc()}")
            text, is_error = "That request couldn't be processed.", True
        self.send({"jsonrpc": "2.0", "id": request["id"],
                   "result": {"content": [{"type": "text", "text": text}], "isError": is_error}})

    def serve(self) -> None:
        for raw in self.stdin:
            if not raw.strip():
                continue
            request = json.loads(raw)
            method, rid = request.get("method"), request.get("id")
            if method == "tools/call":
                threading.Thread(target=self._tool, args=(request,), daemon=True).start()
            elif rid is None:
                continue
            elif method == "initialize":
                # Starts the loop right away, so reports and truth are gathered before the commander's first call.
                with contextlib.suppress(Exception):
                    self.get_runtime()
                self.send({"jsonrpc": "2.0", "id": rid, "result": {
                    "protocolVersion": (request.get("params") or {}).get("protocolVersion", "2025-06-18"),
                    "capabilities": {"experimental": {"claude/channel": {}}, "tools": {}},
                    "serverInfo": {"name": "commander", "version": "0.1.0"}, "instructions": DOCTRINE}})
            elif method == "tools/list":
                self.send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
            elif method == "ping":
                self.send({"jsonrpc": "2.0", "id": rid, "result": {}})
            else:
                self.send({"jsonrpc": "2.0", "id": rid,
                           "error": {"code": -32601, "message": f"unknown method {method}"}})
        self.stop.set()


def main() -> None:
    Server().serve()


if __name__ == "__main__":
    main()
