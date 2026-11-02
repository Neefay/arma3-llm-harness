"""MCP server (stdio) exposing the harness to LLM agents. Tools are thin wrappers over Harness."""
from __future__ import annotations

import functools
import json
import traceback
from typing import Any

from mcp.server.mcpserver import Image, MCPServer

from . import scenario
from .adapters import rounds_framework as rounds
from .bridge import BridgeError
from .harness import Harness, HarnessError

INSTRUCTIONS = """\
Arma 3 dev harness. Typical flow:
1. arma_status: what is running, and the mission profiles. arma_start(mission=...) boots a headless dedicated
   server (~20 s). hcs=N adds headless clients; client=true adds a rendering client (opens a game
   window) needed for arma_snapshot and arma_gui_text.
2. arma_exec runs SQF (unscheduled by default) on target server | clients | hcs | all | interface |
   owner:N | player:<name> and returns one result per machine, with script errors attributed to the call.
   Comments are fine. Lint non-trivial SQF first if an SQF linter tool is available.
3. Observe with arma_events (cursor-based; pass back "next") and arma_wait_for (block on a match).
   Events: k=evt (type=fsm|ctx|attached from the rounds adapter), k=err (script errors), k=res, k=hello.
4. See: arma_snapshot (in-engine screenshot incl. GUI, optional camera position), arma_gui_text,
   arma_map (terrain SVG + named locations).
5. arma_reload hot-reloads a mission file from the source folder; arma_run_scenario runs a YAML test.
6. arma_stop when done. The game keeps running if this MCP server restarts.
rounds_* tools read the rounds framework through its own accessors.
"""

server = MCPServer(name="arma", instructions=INSTRUCTIONS)
_harness: Harness | None = None


def h() -> Harness:
    global _harness
    if _harness is None:
        _harness = Harness()
    return _harness


def safe(fn):
    """Turn harness errors into structured tool output instead of opaque exceptions."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (HarnessError, BridgeError, KeyError, ValueError, FileNotFoundError) as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:  # keep the server alive; report with context
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}
    return wrapper


@server.tool()
@safe
def arma_status() -> dict:
    """Run state: mode, mission, processes, bridge health, connected machines (owner ids, kinds)."""
    return h().status()


@server.tool()
@safe
def arma_start(mission: str | None = None, hcs: int = 0, client: bool = False,
               overrides: dict | None = None) -> dict:
    """Boot a mission profile on an isolated local dedicated server and wait until the bridge is up.

    mission: profile name from harness.toml (see arma_status); omitted = the configured default.
    hcs: headless clients to join (the mission needs HeadlessClient_F slots).
    client: also start a rendering game client (a window opens on the desktop); needed for snapshots.
    overrides: mission context values applied before the first round, e.g. {"ROUND_DURATION": 3}
      (rounds_framework adapter)."""
    return h().start(mission=mission, hcs=hcs, client=client, overrides=overrides)


@server.tool()
@safe
def arma_stop() -> dict:
    """Stop the server, headless clients and clients of the current run (or detach from an attached game)."""
    return h().stop()


@server.tool()
@safe
def arma_hc_start() -> dict:
    """Add one headless client to the running server (tests JIP when the mission is already in progress)."""
    return h().hc_start()


@server.tool()
@safe
def arma_client_start() -> dict:
    """Add a rendering game client (opens a window) to the running server, for snapshots and GUI checks."""
    return h().client_start()


@server.tool()
@safe
def arma_attach(pid: int | None = None, adapters: list[str] | None = None) -> dict:
    """Attach to a game the user started themselves (SP, Eden preview, or hosting MP) that loads @Pythia
    and @brmh. pid is optional when exactly one Arma process runs."""
    return h().attach(pid=pid, adapters_=adapters)


@server.tool()
@safe
def arma_exec(code: str, target: str = "server", timeout_s: float = 10, scheduled: bool = False,
              args: list | None = None) -> dict:
    """Execute SQF and return {ok, results: [{m, o, r, errors, ms, aborted?}], owners, error?}.

    target: server | clients | hcs | all | interface | owner:<n> | player:<name>.
    args are passed as _this. The last expression is the result (objects come back as
    {"$obj", "$type", "$netId"}). Script errors raised during the call are listed per machine;
    aborted=true means an error stopped the code. scheduled=true spawns the code (sleep/waitUntil allowed)."""
    return h().exec(code, target=target, timeout=timeout_s, scheduled=scheduled, args=args)


@server.tool()
@safe
def arma_events(since: int | None = None, kinds: list[str] | None = None, types: list[str] | None = None,
                limit: int = 100, wait_s: float = 0) -> dict:
    """Read the event stream from cursor `since` (omit for "from now"; 0 = everything kept).
    kinds filter envelope kind (evt, err, res, hello, bye, ext, dispatch, mission); types filter evt type
    (fsm, ctx, attached). wait_s long-polls for new events. Pass the returned `next` back as `since`."""
    return h().events(since=since, kinds=kinds, types=types, limit=limit, wait=wait_s)


@server.tool()
@safe
def arma_wait_for(match: dict, since: int | None = None, timeout_s: float = 30) -> dict:
    """Block until an event matches. match: field -> value or operator ({"$in": [...]}, {"$re": "..."},
    {"$contains": x}, {"$gt": n}, {"$exists": true}, ...); dotted keys reach nested fields.
    Example: {"k": "evt", "type": "fsm", "dir": "enter", "state": "ROUND_END"}.
    since: cursor (omit = from now, 0 = also consider events already received)."""
    return h().wait_for(match, since=since, timeout=timeout_s)


@server.tool()
@safe
def arma_errors(since: int = 0, limit: int = 50) -> dict:
    """Script errors (ScriptError handler) from every machine, with request attribution, file, line,
    nearby code and stack."""
    return h().events(since=since, kinds=["err"], limit=limit)


@server.tool()
@safe
def arma_rpt(machine: str = "server", grep: str | None = None, tail: int = 80) -> dict:
    """Raw RPT log lines of a machine of the run (server, hc1, client1, ...), optionally regex-filtered."""
    return h().rpt(machine=machine, grep=grep, tail=tail)


@server.tool()
@safe
def arma_snapshot(camera_pos: list[float] | None = None, camera_target: list[float] | None = None,
                  fov: float = 0.75, max_width: int = 1280, hide_hud: bool = False) -> list:
    """In-engine screenshot from the rendering client (GUI included). camera_pos [x,y,z] (ATL) shows the
    scene from a temporary camera aimed at camera_target, then restores the view. Returns the image."""
    snap = h().snapshot(camera_pos=camera_pos, camera_target=camera_target, fov=fov, max_width=max_width,
                        hide_hud=hide_hud)
    return [Image(path=snap["path"]), json.dumps(snap)]


@server.tool()
@safe
def arma_gui_text(target: str = "interface", text_only: bool = True) -> dict:
    """Text dump of open displays and visible controls (idc, class, type, text, position, fade)."""
    return h().gui_text(target=target, text_only=text_only)


@server.tool()
@safe
def arma_map(contours: bool = True, trees: bool = False) -> dict:
    """Export the terrain map as SVG (works headless) and list named locations in world coordinates."""
    return h().map_svg(contours=contours, trees=trees)


@server.tool()
@safe
def arma_reload(path: str, target: str = "all", function: str | None = None, force: bool = False) -> dict:
    """Hot-reload a mission file from the mission's source folder (path relative to it), on `target`.
    With function="TAG_fnc_name" the file becomes that CfgFunctions function. Files with top-level
    statements other than function definitions are refused unless force=true."""
    return h().reload(path, target=target, function=function, force=force)


@server.tool()
@safe
def arma_run_scenario(path: str, keep_running: bool = False) -> dict:
    """Run a YAML scenario (setup, steps, assertions) and return a pass/fail report. Starts and stops
    its own run unless one is already active (then it uses that one). Paths are relative to scenarios/."""
    return scenario.run(h(), path, keep_running=keep_running)


@server.tool()
@safe
def rounds_state() -> dict:
    """Rounds framework: FSM state, trimmed context, controllers, command namespaces, mission time."""
    return rounds.state(h())


@server.tool()
@safe
def rounds_context_get(key: str) -> dict:
    """Rounds framework: read one context value (e.g. TEAM_WINS, ROUNDS_DATA, CURRENT_ROUND)."""
    return rounds.context_get(h(), key)


@server.tool()
@safe
def rounds_context_set(key: str, value: Any) -> dict:
    """Rounds framework: set a context value (JSON value; objects become hashmaps)."""
    return rounds.context_set(h(), key, value)


@server.tool()
@safe
def rounds_fire_event(event: str, args: list | None = None, alias: str = "GameController") -> dict:
    """Rounds framework: fire a controller event, e.g. "round.force_end" (BRM_fnc_controllerEvent)."""
    return rounds.fire_event(h(), event, args, alias)


@server.tool()
@safe
def rounds_gui(target: str = "interface") -> dict:
    """Rounds framework: SimpleGUI groups with their controls' text, visibility, fade and DATA."""
    return rounds.gui(h(), target)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
