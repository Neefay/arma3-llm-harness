"""Command line: the same operations as the MCP tools, printing JSON.

    arma-harness start --mission rounds_framework --hcs 1 --client --override ROUND_DURATION=5
    arma-harness exec "count allPlayers" --target server
    arma-harness events --kinds evt --types fsm
    arma-harness wait '{"k":"evt","type":"fsm","dir":"enter","state":"GAME"}' --timeout 60
    arma-harness snapshot --camera 4500,3800,30 --look 4520,3830,0
    arma-harness scenario boot
    arma-harness stop
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import agents, scenario
from .adapters import rounds_framework as rounds
from .bridge import BridgeError
from .harness import Harness, HarnessError


def _vec(s: str | None) -> list[float] | None:
    return [float(x) for x in s.split(",")] if s else None


def _value(s: str):
    try:
        return json.loads(s)
    except ValueError:
        return s


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="arma-harness", description="Drive and observe Arma 3.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    s = sub.add_parser("start")
    s.add_argument("--mission", help="profile name (default: harness.toml default_mission)")
    s.add_argument("--hcs", type=int, default=0)
    s.add_argument("--client", action="store_true")
    s.add_argument("--override", action="append", default=[], metavar="KEY=JSON")
    sub.add_parser("stop")
    sub.add_parser("hc")
    sub.add_parser("client")
    a = sub.add_parser("attach")
    a.add_argument("--pid", type=int)
    a.add_argument("--adapter", action="append", default=[])
    sub.add_parser("machines")
    e = sub.add_parser("exec")
    e.add_argument("code", help="SQF, or @file.sqf")
    e.add_argument("--target", default="server")
    e.add_argument("--timeout", type=float, default=10)
    e.add_argument("--scheduled", action="store_true")
    ev = sub.add_parser("events")
    ev.add_argument("--since", type=int)
    ev.add_argument("--kinds", nargs="*")
    ev.add_argument("--types", nargs="*")
    ev.add_argument("--limit", type=int, default=50)
    ev.add_argument("--wait", type=float, default=0)
    w = sub.add_parser("wait")
    w.add_argument("match", help="JSON match spec")
    w.add_argument("--since", type=int)
    w.add_argument("--timeout", type=float, default=30)
    er = sub.add_parser("errors")
    er.add_argument("--since", type=int, default=0)
    r = sub.add_parser("rpt")
    r.add_argument("--machine", default="server")
    r.add_argument("--grep")
    r.add_argument("--tail", type=int, default=60)
    sn = sub.add_parser("snapshot")
    sn.add_argument("--camera")
    sn.add_argument("--look")
    sn.add_argument("--fov", type=float, default=0.75)
    sn.add_argument("--max-width", type=int, default=1280)
    sn.add_argument("--hide-hud", action="store_true")
    g = sub.add_parser("gui")
    g.add_argument("--target", default="interface")
    g.add_argument("--all", action="store_true", help="include controls without text")
    sub.add_parser("map")
    sub.add_parser("guide", help="print the agent cheat sheet (AGENTS.md)")
    sa = sub.add_parser("setup-agents", help="write project MCP config for agent clients (never overwrites)")
    sa.add_argument("clients", nargs="*", help="claude codex gemini cursor opencode vscode (default: all)")
    sa.add_argument("--force", action="store_true", help="replace differing files (old kept as .bak)")
    sa.add_argument("--dry-run", action="store_true")
    sub.add_parser("observe", help="install the chat and kill observers")
    li = sub.add_parser("listen", help="wait for a chat message addressed to Claude")
    li.add_argument("--name", default="Claude")
    li.add_argument("--since", type=int)
    li.add_argument("--timeout", type=float, default=25)
    sy = sub.add_parser("say", help="show a chat line from Claude to players")
    sy.add_argument("text")
    sy.add_argument("--sender", default="Claude")
    sy.add_argument("--hint", action="store_true")
    sy.add_argument("--target", default="interface")
    vw = sub.add_parser("view", help="what the player's camera sees, as data")
    vw.add_argument("--radius", type=float, default=300)
    vw.add_argument("--max", type=int, default=40)
    vw.add_argument("--target", default="interface")
    rl = sub.add_parser("reload")
    rl.add_argument("path")
    rl.add_argument("--target", default="all")
    rl.add_argument("--function")
    rl.add_argument("--force", action="store_true")
    sc = sub.add_parser("scenario")
    sc.add_argument("path")
    sc.add_argument("--keep-running", action="store_true")
    co = sub.add_parser("commander", help="set up, watch and review a commander battle (docs/COMMANDER.md)")
    co.add_argument("action", choices=["start", "status", "aar", "stop"])
    co.add_argument("scenario", nargs="?", help="scenario name in scenarios/commander/, or a path (start only)")
    co.add_argument("--mode", choices=["hold", "deliver"], help="what happens to messages during a turn")
    rs = sub.add_parser("rounds")
    rs.add_argument("what", choices=["state", "get", "set", "fire", "gui"])
    rs.add_argument("arg", nargs="*")

    args = p.parse_args(argv)
    if args.cmd == "guide":
        sys.stdout.reconfigure(encoding="utf-8")
        print(agents.guide())
        return 0
    h = Harness()
    try:
        out = _dispatch(h, args)
    except (HarnessError, BridgeError, KeyError, ValueError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(out if isinstance(out, str) else json.dumps(out, indent=2, default=str))
    if args.cmd == "scenario":
        return 0 if out.get("as_expected") else 1
    return 0


def _dispatch(h: Harness, a):
    match a.cmd:
        case "status":
            return h.status()
        case "start":
            overrides = {k: _value(v) for k, v in (o.split("=", 1) for o in a.override)}
            return h.start(mission=a.mission, hcs=a.hcs, client=a.client, overrides=overrides)
        case "stop":
            return h.stop()
        case "hc":
            return h.hc_start()
        case "client":
            return h.client_start()
        case "attach":
            return h.attach(pid=a.pid, adapters_=a.adapter)
        case "machines":
            return h.machines()
        case "exec":
            code = Path(a.code[1:]).read_text(encoding="utf-8") if a.code.startswith("@") else a.code
            return h.exec(code, a.target, timeout=a.timeout, scheduled=a.scheduled)
        case "events":
            return h.events(since=a.since, kinds=a.kinds, types=a.types, limit=a.limit, wait=a.wait)
        case "wait":
            return h.wait_for(json.loads(a.match), since=a.since, timeout=a.timeout)
        case "errors":
            return h.events(since=a.since, kinds=["err"])
        case "rpt":
            return h.rpt(machine=a.machine, grep=a.grep, tail=a.tail)
        case "snapshot":
            return h.snapshot(camera_pos=_vec(a.camera), camera_target=_vec(a.look), fov=a.fov,
                              max_width=a.max_width, hide_hud=a.hide_hud)
        case "gui":
            return h.gui_text(target=a.target, text_only=not a.all)
        case "map":
            return h.map_svg()
        case "observe":
            return h.observe()
        case "setup-agents":
            return agents.setup(a.clients or None, force=a.force, dry_run=a.dry_run)
        case "listen":
            return h.listen(name=a.name, since=a.since, timeout=a.timeout)
        case "say":
            return h.say(a.text, sender=a.sender, hint=a.hint, target=a.target)
        case "view":
            return h.view(radius=a.radius, max_objects=a.max, target=a.target)
        case "reload":
            return h.reload(a.path, target=a.target, function=a.function, force=a.force)
        case "scenario":
            return scenario.run(h, a.path, keep_running=a.keep_running)
        case "commander":
            return _commander(h, a)
        case "rounds":
            match a.what:
                case "state":
                    return rounds.state(h)
                case "get":
                    return rounds.context_get(h, a.arg[0])
                case "set":
                    return rounds.context_set(h, a.arg[0], _value(a.arg[1]))
                case "fire":
                    return rounds.fire_event(h, a.arg[0], [_value(x) for x in a.arg[1:]])
                case "gui":
                    return rounds.gui(h)
    raise ValueError(a.cmd)


def _commander(h: Harness, a):
    from .commander import operator

    match a.action:
        case "start":
            if not a.scenario:
                raise ValueError("commander start needs a scenario name")
            return operator.start(a.scenario, a.mode, h)
        case "status":
            return operator.status(h.home)
        case "aar":
            return operator.aar(h.home)
        case "stop":
            return operator.stop(h)
    raise ValueError(a.action)


if __name__ == "__main__":
    sys.exit(main())
