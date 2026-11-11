"""MCP server (stdio) exposing the harness to LLM agents. Tools are thin wrappers over Harness."""
from __future__ import annotations

import asyncio
import functools
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import anyio
from mcp.server.mcpserver import Context, Image, MCPServer
from mcp.server.stdio import stdio_server

from . import agents, chatwake, library, scenario
from .adapters import rounds_framework as rounds
from .bridge import BridgeError
from .harness import Harness, HarnessError, check_agent_name

INSTRUCTIONS = """\
Arma 3 dev harness. Typical flow:
1. arma_status: what is running, and the mission profiles. arma_start(mission=...) boots a headless dedicated
   server (~20 s). hcs=N adds headless clients; client=true adds a rendering client (opens a game
   window) needed for arma_snapshot and arma_gui_text.
2. arma_commands finds a tested command for a common job (spawning, weather, tasks, buildings, cleanup...) and
   arma_run runs it by name with checked arguments: try these before writing SQF.
   arma_exec runs SQF (unscheduled by default) on target server | clients | hcs | all | interface |
   owner:N | player:<name> and returns one result per machine, with script errors attributed to the call.
   Comments are fine. Lint non-trivial SQF first if an SQF linter tool is available.
3. Observe with arma_events (cursor-based; pass back "next") and arma_wait_for (block on a match).
   Events: k=evt (type=fsm|ctx|attached from the rounds adapter), k=err (script errors), k=res, k=hello.
4. See: arma_snapshot (in-engine screenshot incl. GUI, optional camera position), arma_gui_text,
   arma_map (terrain SVG + named locations).
5. Conversation: arma_set_name picks the name players call you by (default Claude). arma_chat_wake
   makes each chat message to you start your turn, in Claude Code and OpenCode: use it instead of an
   arma_listen loop when it says ok. arma_listen waits for a message (any client), arma_say replies in
   game, arma_view gives the player's view as data (with screen coordinates of what is on screen).
   A wake arrives as a <channel source="arma"> block holding the message: answer it with arma_say.
6. arma_reload hot-reloads a mission file from the source folder; arma_run_scenario runs a YAML test.
7. arma_stop when done. The game keeps running if this MCP server restarts.
rounds_* tools read the rounds framework through its own accessors.
"""

server = MCPServer(name="arma", instructions=INSTRUCTIONS)
_harness: Harness | None = None
# This session's name: what players type in game ("Zeus, ..."), and the sender of its replies.
# Set with arma_set_name, or BRMH_AGENT_NAME when the client starts the server.
_agent_name = os.environ.get("BRMH_AGENT_NAME", "").strip() or "Claude"
_wake: chatwake.ChatWake | None = None
_wake_via: str | None = None

# The harness's own files, as this server loaded them. OpenCode's background service keeps a folder's MCP servers
# running across sessions and after its app is closed, so a server can go on running code the harness has since
# changed: chat in an agent's channel didn't reach a GPT-6 session for that, while a fresh Claude Code one heard it.
_PACKAGE = Path(__file__).parent
RESTART = ("Restart this MCP server to load it: in OpenCode, run `opencode service restart` (or close and reopen the "
           "desktop app); in Claude Code, /mcp and reconnect arma, or start a new session.")


def _code_stamp() -> float:
    return max((path.stat().st_mtime for pattern in ("*.py", "*.sqf")
                for path in _PACKAGE.rglob(pattern)), default=0.0)


_LOADED = _code_stamp()


def code_changed() -> str | None:
    """Whether the harness's code on disk is newer than what this server loaded, said for the agent to pass on."""
    if _code_stamp() <= _LOADED:
        return None
    return f"The harness's code has changed since this MCP server started, so it's running the old version. {RESTART}"


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
def arma_guide() -> str:
    """The agent cheat sheet (AGENTS.md): golden rules, where code runs, the in-game chat loop, and tested
    SQF recipes. Read it once at the start of a session, before using the other arma_* tools."""
    return agents.guide()


@server.tool()
@safe
def arma_status() -> dict:
    """Run state: mode, mission, processes, bridge health, connected machines (owner ids, kinds), and
    `listener`: chat_observer_installed (per machine), listen_call_waiting_now, and messages to Claude
    since the last arma_listen started (unread if no call is waiting). `server_code` says if this MCP server is
    running older code than the harness now has: pass that on to the user."""
    status = h().status()
    stale = code_changed()
    return {**status, "server_code": stale or "current"}


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
def arma_commands(query: str = "") -> dict:
    """The command library: tested commands for common jobs, to run with arma_run instead of writing SQF. With no
    query, the index of every command by area. With words, such as "spawn car", "night fog" or "this guy", the
    best matches in full: what each does, its parameters with types and defaults, what it returns, and an example.
    References are things you can say: "player", a unit's or player's name, a net id, a grid such as "034 030", or
    a "made:N" handle a command returned."""
    return library.search(query)


@server.tool()
@safe
def arma_run(name: str, args: dict | list | None = None) -> dict:
    """Run a library command by name (see arma_commands) on the machine it belongs on, with its arguments checked
    first: {"class": "C_Offroad_01_F"} by name, or a list in parameter order; anything left out takes its default.
    Returns {ok: true, result} or {ok: false, error} with what to fix. Things it makes come back with a "made:N"
    handle: delete_made removes them."""
    return library.run(h(), name, args)


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
def arma_set_name(name: str, force: bool = False) -> dict:
    """Choose the name this session answers to in game, e.g. "Zeus": players then type "Zeus, spawn me a
    car", and your replies show as "Zeus: ..." in your own colour. Several sessions can listen at once,
    each under its own name; "everyone, ..." reaches all of them. Refused if another live session holds
    the name (force=true only if that session is gone). Default name: Claude."""
    global _agent_name
    claimed = h().claim_name(check_agent_name(name), force=force)
    _agent_name = claimed["name"]
    return {"ok": True, **claimed}


@server.tool()
@safe
def arma_listen(since: int | None = None, timeout_s: float = 25, name: str | None = None) -> dict:
    """Wait for a player to type a chat message addressed to you: your name (see arma_set_name; default
    "Claude") at the start, as in "zeus, ...", "@zeus ...", "hey zeus ...", or "everyone, ...". Returns
    the message, the kills since `since`, and `next`: pass it back as `since` on the following call so
    nothing said meanwhile is missed. Reply with arma_say; look with arma_view and arma_snapshot.
    Players can also type to you in your own radio channel, named after you, without your name: it's made when
    you first listen. This is NOT a background service: you are listening only while this call is running.
    found=false just means the timeout passed with no message; it does not prove anything works. To answer "is the
    listener on?", use arma_status -> listener (observer per machine; per named session: a call waiting
    now, unread messages).
    The call BLOCKS for up to timeout_s seconds (default 25, max 300); you can do nothing else meanwhile.
    Keep timeout_s below your client's tool-call timeout (Codex: 60 s by default) or the client
    cancels the call. Chat is captured while you are not listening, so short calls lose nothing.
    timeout_s=0 checks for messages and returns at once (no waiting)."""
    who = name or _agent_name
    heard = h().listen(name=who, since=since, timeout=max(0.0, min(float(timeout_s), 300.0)))
    if h()._listener(who).get("channel"):
        heard["your_channel"] = (f"Players can type to you in the {who} radio channel without starting with your "
                                 "name. Tell the user that once, in one line, when you start listening.")
    return heard


@server.tool()
@safe
def arma_say(text: str, hint: bool = False, target: str = "interface", sender: str | None = None) -> dict:
    """Show players a chat line "<your name>: <text>" in your colour (sender defaults to your session
    name, see arma_set_name). hint=true also shows a hint box (for longer answers). Keep lines short:
    the chat feed shows about one sentence comfortably."""
    return h().say(text, sender=sender or _agent_name, hint=hint, target=target)


@server.tool()
@safe
def arma_view(radius: float = 300, max_objects: int = 40, target: str = "interface") -> dict:
    """The player's view as data: position, grid, facing, world time/weather, and on-screen buildings,
    vehicles and units with world positions, screen [x, y] (0..1), distance, line-of-sight `seen` (0..1)
    and building position counts. Use it with arma_snapshot to turn "that house" into coordinates."""
    return h().view(radius=radius, max_objects=max_objects, target=target)


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


def _log(text: str) -> None:
    print(text, file=sys.stderr, flush=True)  # the client's MCP log: never the agent's


@server.tool()
async def arma_chat_wake(on: bool = True, test: bool = True, ctx: Context = None) -> dict:
    """Make every chat message to you (your name, see arma_set_name) start your turn, carrying the message, instead
    of waiting in an arma_listen loop: you hear players even between turns, and nothing runs, or costs, while it's
    quiet. Works in Claude Code (launched with --dangerously-load-development-channels server:arma) and OpenCode;
    for other clients it says so, and you use arma_listen. A wake arrives as a <channel source="arma"> block: answer
    it with arma_say, then end your turn. on=false turns it off. It needs a game attached or started, keeps working
    through a mission restart, and ends when that game closes or is detached: turn it on again for the next one.
    test=true (the default) also sends you one test wake right away: if it doesn't reach you
    shortly after this turn ends, wakes don't work in this session, so turn them off and use arma_listen."""
    global _wake, _wake_via
    if not on:
        if _wake is not None:
            _wake.stop.set()
        _wake, _wake_via = None, None
        h().set_wake(_agent_name, None)
        return {"ok": True, "on": False}
    params = ctx.session.client_params if ctx is not None else None
    client = ((params.client_info.name if params and params.client_info else "") or "").lower()
    if "opencode" in client:
        from .commander import opencode

        service = opencode.Service(opencode.find_cli() or "opencode")
        route = opencode.Wakes(service, os.getcwd(), _log, source="arma", lone=True, display=lambda text: text)
        try:  # this call is part of the session's running turn, so it's the one running now
            route.session = await asyncio.to_thread(route.find_session)
        except Exception as exc:
            return {"ok": False, "error": f"OpenCode's server couldn't be reached: {exc}. Use arma_listen."}
        if route.session is None:
            return {"ok": False, "error": "couldn't tell which OpenCode session this is (more than one is running "
                                          "here?). Use arma_listen."}

        def deliver(text: str, meta: dict, display: str) -> None:
            route.send(text, meta, display=display)

        via = f"opencode session {route.session}"
    elif "claude" in client:
        loop, outbound = asyncio.get_running_loop(), ctx.session._connection.outbound

        def deliver(text: str, meta: dict, display: str) -> None:
            future = asyncio.run_coroutine_threadsafe(
                outbound.notify("notifications/claude/channel", {"content": text, "meta": meta}), loop)
            future.result(timeout=10)

        via = "claude code channel"
    else:
        return {"ok": False, "error": f"this client ({client or 'unknown'}) can't be woken from outside: use an "
                                      "arma_listen loop, as AGENTS.md describes"}
    h().forget_dead_run()
    if h().state() is None:
        return {"ok": False, "error": "no game: attach to it (arma_attach) or start one first. A wake belongs to the "
                                      "game it's turned on in, and ends when that game closes or is detached."}
    if _wake is not None:
        _wake.stop.set()
    listener = Harness()  # its own: the thread waits on the bridge while tools use theirs

    def current_run() -> str | None:
        listener.forget_dead_run()  # a closed game's run is kept until someone notices: notice here
        state = listener.state()
        return state.run_id if state else None

    def ended(why: str) -> None:
        global _wake_via
        _wake_via = None
        h().set_wake(_agent_name, None)

    h().claim_name(_agent_name)
    _wake = chatwake.ChatWake(listener.listen, lambda: _agent_name, deliver, _log, run=current_run,
                              ended=ended).start()
    _wake_via = via
    h().set_wake(_agent_name, via)
    note = ("Claude Code delivers these only when it was launched with --dangerously-load-development-channels "
            "server:arma." if via.startswith("claude") else "Messages that arrive mid-turn wait for the turn to end.")
    note += (f" Players can type to you in the {_agent_name} radio channel without starting with your name; tell "
             "the user that, in one line.")
    stale = code_changed()
    if stale:
        note += f" Also tell the user: {stale}"
    if test:
        def send_test() -> None:
            time.sleep(1)  # after this call's answer, so the test arrives as a wake of its own
            try:
                deliver(TEST_WAKE, {"from": "harness", "to": _agent_name, "test": "true"}, "💬 Chat wake test")
            except Exception as exc:
                _log(f"chat wake: the test wake couldn't be sent: {exc}")

        threading.Thread(target=send_test, daemon=True).start()
        note += " A test wake is on its way: when it arrives, tell the user wakes work."
    return {"ok": True, "on": True, "name": _agent_name, "via": via, "note": note}


TEST_WAKE = ("Chat wake test: this message reached you through a wake, so players' chat to you will too. Tell the "
             "user, in the terminal or app, that chat wakes work, then end your turn. Don't answer it in game.")


async def _serve() -> None:
    """As server.run("stdio"), declaring the channel capability Claude Code wakes a session through, and serving only
    the initialize handshake.

    A channel needs a connection that stays open both ways: Claude Code doesn't register a server that settles on the
    stateless 2026-07-28 revision as one, and says nothing. The library would let the client's first request choose:
    Claude Code opens with a stateless server/discover, and the connection would be stateless for good, refusing the
    initialize it falls back to with -32022, the one error clients don't fall back from. That's how removing the
    discover handler alone broke the arma tools in Claude Code. Serving the handshake era from the start, a stateless
    first request gets "invalid request" instead, which clients do fall back from, to initialize. The library answers
    that with the newest revision that has a handshake. tests/test_chatwake.py replays Claude Code's opening."""
    from mcp.server.runner import _serve_legacy_stream  # the library's own era-specific loop

    low = server._lowlevel_server
    low._request_handlers.pop("server/discover", None)  # and a plain one gets "method not found"
    options = low.create_initialization_options(experimental_capabilities={"claude/channel": {}})
    async with stdio_server() as (read_stream, write_stream), low.lifespan(low) as state:
        try:
            await _serve_legacy_stream(low, read_stream, write_stream, lifespan_state=state, session_id=None,
                                       init_options=options, raise_exceptions=False)
        finally:
            await write_stream.aclose()


def main() -> None:
    anyio.run(_serve)


if __name__ == "__main__":
    main()
