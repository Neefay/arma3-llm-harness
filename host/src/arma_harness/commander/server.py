"""The commander's MCP server: its entire interface to the world, plus the channel that wakes it.

Plain JSON-RPC over stdio, because channels need an experimental capability and a custom notification.
Keep TOOLS the complete list: a test fails if anything else appears. Errors here never carry engine details.
"""
from __future__ import annotations

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

_STRING = {"type": "string"}
_LEG = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "description": "MOVE, HOLD, SEARCH, SENTRY, PATROL, HALT or POSTURE"},
        "at": {"description": "Grid such as '034 030', or a marker id. For PATROL, a list of them."},
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
     "comes back as No answer.", "inputSchema": {"type": "object", "properties": {
        "to": {"type": "string", "description": "A callsign, or all"},
        "topics": {"type": "array", "items": _STRING,
                   "description": "position, task, strength, ammo, contacts or eta"},
     }, "required": ["to"]}},
    {"name": "commander_schedule", "description": "Set a wake. Give after (such as 1:30) or at (such as T+15:45), and "
     "do={'wake': 'why you want to wake'}. Your note comes back with the wake.", "inputSchema": {
        "type": "object", "properties": {"after": _STRING, "at": _STRING, "do": {"type": "object"}},
        "required": ["do"]}},
    {"name": "commander_unschedule", "description": "Cancel a wake by its id.", "inputSchema": {
        "type": "object", "properties": {"id": _STRING}, "required": ["id"]}},
    {"name": "commander_end_turn", "description": "End your turn, with a short note. Refused when no wake is set, "
     "unless messages_only is true, which means you'll wake only for incoming messages.", "inputSchema": {
        "type": "object", "properties": {"note": _STRING, "messages_only": {"type": "boolean"}}}},
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
                return runtime.schedule(args.get("do"), args.get("after"), args.get("at"))
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
