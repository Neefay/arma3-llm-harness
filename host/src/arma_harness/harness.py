"""The harness facade: everything the MCP server, the CLI and the scenario runner use.

Run state lives in ``<home>/state.json`` so any process (a restarted MCP server, the CLI) can
reconnect to a running game. Game processes are owned by the OS, not by us (see procutil.spawn).
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import socket
import threading
import time
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

from . import adapters, missions, procutil, serverroot
from .audit import Audit
from .bridge import Bridge, BridgeError
from .config import Config, Home, load_config
from .matching import matcher
from .sqf import PreprocessError, preprocess, side_effects, strip_comments

SERVER_EXE = "arma3server_x64.exe"
CLIENT_EXE = "arma3_x64.exe"


class HarnessError(RuntimeError):
    pass


@dataclass
class Proc:
    pid: int
    kind: str          # server | hc | client
    name: str
    profile: str       # -profiles dir (RPTs land here)
    exe: str


@dataclass
class RunState:
    run_id: str
    mode: str                      # launched | attached
    mission: str                   # profile name ("" when attached)
    folder: str                    # mission folder name
    game_port: int = 0
    password: str = ""
    token: str = ""
    bridge_port: int = 0
    bridge_pid: int = 0
    run_dir: str = ""
    adapters: list[str] = field(default_factory=list)
    overrides: dict = field(default_factory=dict)
    procs: list[Proc] = field(default_factory=list)
    started: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> RunState:
        d = json.loads(text)
        d["procs"] = [Proc(**p) for p in d.get("procs", [])]
        return cls(**d)


def _snippet(name: str) -> str:
    return strip_comments(resources.files("arma_harness.snippets").joinpath(name).read_text(encoding="utf-8"))


def _udp_free(port: int) -> bool:
    for addr in ("0.0.0.0", "127.0.0.1"):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind((addr, port))
            except OSError:
                return False
    return True


def _pick_game_port(start: int = 2402) -> int:
    for base in range(start, start + 400, 10):
        if all(_udp_free(base + i) for i in range(4)):
            return base
    raise HarnessError("no free UDP port block found for the game server")


class Harness:
    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.home: Home = self.config.home
        self.audit = Audit(self.home.logs / "audit.jsonl")

    # -- state ---------------------------------------------------------------------------------

    def state(self) -> RunState | None:
        f = self.home.state_file
        return RunState.from_json(f.read_text(encoding="utf-8")) if f.exists() else None

    def _save(self, st: RunState | None) -> None:
        if st is None:
            self.home.state_file.unlink(missing_ok=True)
        else:
            tmp = self.home.state_file.with_suffix(".tmp")
            tmp.write_text(st.to_json(), encoding="utf-8")
            tmp.replace(self.home.state_file)

    def _require(self) -> RunState:
        st = self.state()
        if st is None:
            raise HarnessError("nothing running: start a mission (arma_start) or attach to a game (arma_attach)")
        return st

    def bridge(self) -> Bridge:
        st = self._require()
        if not st.bridge_port:
            port = self._read_port_file(st.bridge_pid)
            if not port:
                raise HarnessError("the game's bridge is not up yet (mission still loading?)")
            st.bridge_port = port
            self._save(st)
        return Bridge(st.bridge_port, st.token)

    def _session_files(self, pid: int) -> tuple[Path, Path]:
        return self.home.sessions / f"{pid}.json", self.home.sessions / f"{pid}.port.json"

    def _read_port_file(self, pid: int) -> int:
        _, port_file = self._session_files(pid)
        try:
            return int(json.loads(port_file.read_text(encoding="utf-8"))["port"])
        except (OSError, ValueError, KeyError):
            return 0

    def _write_session(self, pid: int, token: str, boot: list[dict]) -> None:
        session_file, port_file = self._session_files(pid)
        port_file.unlink(missing_ok=True)
        tmp = session_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"token": token, "port": 0, "boot": boot, "created": time.time()}),
                       encoding="utf-8")
        tmp.replace(session_file)

    def _wait_bridge(self, st: RunState, timeout: float) -> Bridge:
        deadline = time.time() + timeout
        while time.time() < deadline:
            port = self._read_port_file(st.bridge_pid)
            if port:
                st.bridge_port = port
                self._save(st)
                b = Bridge(port, st.token)
                if b.alive():
                    return b
            if not procutil.alive(st.bridge_pid):
                raise HarnessError(f"game process {st.bridge_pid} exited during startup; see arma_rpt")
            time.sleep(0.5)
        raise HarnessError(f"bridge did not come up within {timeout:.0f}s (is @Pythia and @brmh loaded?)")

    # -- lifecycle -----------------------------------------------------------------------------

    def forget_dead_run(self) -> bool:
        """A run whose game has exited is over, however it went: a server we launched, or a game the user attached us
        to and has since closed. Without this it blocks the next start or attach, with an error about a bridge that
        nothing will ever answer on. Forgetting only drops the record: an attached game still running is left alone,
        and nothing here touches a game."""
        st = self.state()
        if st is None:
            return False
        kind = {"launched": "server", "attached": "attached"}.get(st.mode)
        game = next((p for p in st.procs if p.kind == kind), None)
        if game is None or procutil.alive(game.pid, game.exe or None):
            return False
        self.stop()
        return True

    def start(self, mission: str | None = None, hcs: int = 0, client: bool = False,
              overrides: dict | None = None, timeout: float = 180) -> dict:
        self.forget_dead_run()
        if self.state():
            raise HarnessError("a run is already active; stop it first (arma_stop)")
        profile = self.config.mission(mission)
        mission = profile.name
        mods = [str(self.config.mod_path(m)) for m in profile.mods]
        info = missions.inspect(profile.source)
        if hcs and info["hc_slots"] < hcs:
            raise HarnessError(f"mission has {info['hc_slots']} HeadlessClient_F slot(s), {hcs} requested")
        root = self.home.server_root
        serverroot.ensure(self.config.arma_dir, root)
        missions.stage(profile.source, root / "MPMissions", skip_lobby=profile.skip_lobby,
                       allow_recompile=profile.allow_recompile)

        run_id = time.strftime("%Y%m%d-%H%M%S")
        run_dir = self.home.runs / run_id
        (run_dir / "server").mkdir(parents=True)
        game_port = _pick_game_port()
        password = secrets.token_hex(6)
        token = secrets.token_hex(16)
        cfg = run_dir / "server.cfg"
        cfg.write_text(_server_cfg(profile.folder_name, password), encoding="utf-8")
        args = [str(root / SERVER_EXE), f"-port={game_port}", f"-config={cfg}",
                f"-profiles={run_dir / 'server'}", "-name=server", "-autoInit", "-noSound",
                f"-mod={';'.join(mods)}"]
        merged = {**profile.overrides, **(overrides or {})}
        boot = adapters.boot_items(profile.adapters, merged) + [_observer_boot_item()]
        pid = procutil.spawn(args, root)
        # Written right after spawn: the hub only checks for it once the mission is loading.
        self._write_session(pid, token, boot)
        st = RunState(run_id=run_id, mode="launched", mission=mission, folder=profile.folder_name,
                      game_port=game_port, password=password, token=token, bridge_pid=pid,
                      run_dir=str(run_dir), adapters=profile.adapters, overrides=merged,
                      procs=[Proc(pid, "server", "server", str(run_dir / "server"), SERVER_EXE)],
                      started=time.time())
        self._save(st)
        t0 = time.time()
        bridge = self._wait_bridge(st, timeout)
        out = {"run": run_id, "mission": mission, "server_pid": pid, "game_port": game_port,
               "bridge_port": st.bridge_port, "boot_s": round(time.time() - t0, 1), "mission_info": info}
        for _ in range(hcs):
            out.setdefault("hcs", []).append(self.hc_start(wait=True))
        if client:
            out["client"] = self.client_start(wait=True)
        out["machines"] = self.machines(bridge)
        return out

    def _launch_member(self, kind: str, wait: bool, timeout: float) -> dict:
        st = self._require()
        if st.mode != "launched":
            raise HarnessError("headless clients and clients can only join a run the harness launched")
        profile = self.config.mission(st.mission)
        n = sum(1 for p in st.procs if p.kind == kind) + 1
        name = f"{kind}{n}"
        prof = Path(st.run_dir) / name
        prof.mkdir(parents=True, exist_ok=True)
        if kind == "hc":
            mods = profile.hc_mods if profile.hc_mods is not None else profile.mods
            exe_path, exe = self.home.server_root / SERVER_EXE, SERVER_EXE
            args = [str(exe_path), "-client", "-connect=127.0.0.1", f"-port={st.game_port}",
                    f"-password={st.password}", f"-profiles={prof}", f"-name={name}", "-noSound"]
            cwd = self.home.server_root
        else:
            mods = profile.client_mods
            exe_path, exe = self.config.arma_dir / CLIENT_EXE, CLIENT_EXE
            args = [str(exe_path), "-connect=127.0.0.1", f"-port={st.game_port}", f"-password={st.password}",
                    f"-profiles={prof}", f"-name={name}", "-window", "-noSplash", "-skipIntro", "-noPause",
                    "-noSound", "-world=empty"]
            cwd = prof
        args.append("-mod=" + ";".join(str(self.config.mod_path(m)) for m in mods))
        bridge = self.bridge()
        since = bridge.cursor()
        pid = procutil.spawn(args, cwd)
        st.procs.append(Proc(pid, kind, name, str(prof), exe))
        self._save(st)
        out = {"pid": pid, "name": name}
        if wait:
            # Correlate by kind and "first hello after we spawned it": a headless client's profileName
            # is its slot's name (e.g. HC1), not our -name, so names can't be matched.
            want = "HC" if kind == "hc" else "CLIENT"
            ev, _ = bridge.wait_for(lambda e: e.get("k") == "hello" and e.get("kind") == want, since, timeout)
            if ev is None:
                hint = " (does the mission have a free HeadlessClient_F slot?)" if kind == "hc" else ""
                raise HarnessError(f"{name} did not join within {timeout:.0f}s{hint}")
            out["owner"] = ev.get("o")
        return out

    def hc_start(self, wait: bool = True, timeout: float = 120) -> dict:
        return self._launch_member("hc", wait, timeout)

    def client_start(self, wait: bool = True, timeout: float = 150) -> dict:
        """A rendering game client (opens a window on the desktop) for snapshots and GUI checks."""
        return self._launch_member("client", wait, timeout)

    def attach(self, pid: int | None = None, adapters_: list[str] | None = None, overrides: dict | None = None,
               timeout: float = 30) -> dict:
        """Attach to a game the user started (Eden preview, SP, host-and-play) with @Pythia and @brmh loaded."""
        self.forget_dead_run()  # the last run's game was closed, as when the user quit to start this one
        if self.state():
            raise HarnessError("a run is already active; stop it first")
        if pid is None:
            candidates = procutil.find_processes(CLIENT_EXE) + procutil.find_processes(SERVER_EXE)
            if len(candidates) != 1:
                raise HarnessError(f"pass pid: found {len(candidates)} Arma processes "
                                   f"{[(p.pid, p.info['name']) for p in candidates]}")
            pid = candidates[0].pid
        token = secrets.token_hex(16)
        names = adapters_ or []
        self._write_session(pid, token, adapters.boot_items(names, overrides or {}) + [_observer_boot_item()])
        st = RunState(run_id=time.strftime("%Y%m%d-%H%M%S"), mode="attached", mission="", folder="",
                      token=token, bridge_pid=pid, adapters=names, overrides=overrides or {},
                      procs=[Proc(pid, "attached", "attached", "", "")], started=time.time())
        self._save(st)
        try:
            bridge = self._wait_bridge(st, timeout)
        except HarnessError:
            self._save(None)
            self._session_files(pid)[0].unlink(missing_ok=True)
            raise HarnessError("no bridge: the game must run a mission as host (SP / Eden preview / hosted MP) "
                               "with @Pythia and @brmh loaded") from None
        return {"attached": pid, "bridge_port": st.bridge_port, "status": bridge.status()}

    def stop(self) -> dict:
        st = self.state()
        if st is None:
            return {"stopped": []}
        stopped = []
        if st.mode == "launched":
            for p in reversed(st.procs):
                if procutil.alive(p.pid, p.exe):
                    procutil.kill_tree(p.pid)
                    stopped.append(p.name)
        for p in st.procs:
            for f in self._session_files(p.pid):
                f.unlink(missing_ok=True)
        self._save(None)
        return {"stopped": stopped, "mode": st.mode}

    def status(self) -> dict:
        before = self.state()
        ended = before if self.forget_dead_run() else None
        st = self.state()
        if st is None:
            return {"running": False, "profiles": sorted(self.config.missions),
                    "default_mission": self.config.default_mission,
                    **({"ended_run": f"run {ended.run_id} ({ended.mode}, {ended.mission or 'attached game'}) had "
                                     "ended: its game had exited. Cleared."} if ended else {})}
        procs = [{"name": p.name, "pid": p.pid, "alive": procutil.alive(p.pid, p.exe or None)} for p in st.procs]
        out = {"running": True, "mode": st.mode, "mission": st.mission, "run": st.run_id,
               "uptime_s": round(time.time() - st.started), "processes": procs, "adapters": st.adapters,
               "overrides": st.overrides}
        try:
            b = self.bridge()
            out["bridge"] = b.status()
            out["machines"] = self.machines(b)
            out["listener"] = self.listener_status(b)
        except (BridgeError, HarnessError) as e:
            out["bridge_error"] = str(e)
        return out

    def machines(self, bridge: Bridge | None = None) -> list[dict]:
        b = bridge or self.bridge()
        res = b.exec("brmh_machines", "server", timeout=5)
        r = (res.get("results") or [{}])[0].get("r") or {}
        return [{"owner": int(k), **v} for k, v in sorted(r.items(), key=lambda kv: int(kv[0]))]

    # -- acting --------------------------------------------------------------------------------

    def exec(self, code: str, target: str = "server", timeout: float = 10, scheduled: bool = False,
             args: list | None = None, strip: bool = True) -> dict:
        src = strip_comments(code) if strip else code
        st = self._require()
        res = self.bridge().exec(src, target, timeout, scheduled, args)
        for r in res.get("results") or []:
            if r.get("errors"):
                r["errors"] = _compact_errors(r["errors"])
        self.audit.record(run=st.run_id, target=target, scheduled=scheduled, code=src,
                          ok=res.get("ok"), error=res.get("error"), id=res.get("id"))
        return res

    def reload(self, path: str, target: str = "all", function: str | None = None, force: bool = False) -> dict:
        """Recompile a mission file from the *source* folder into the running game.

        Without ``function`` the file is re-executed (it should only define functions; refused if it has
        other top-level statements unless ``force``). With ``function`` (CfgFunctions name) the file's
        content becomes that function (the staged copy allows recompiling)."""
        st = self._require()
        if st.mode != "launched":
            raise HarnessError("reload needs a launched run (it knows the mission source folder)")
        root = self.config.mission(st.mission).source
        file = (root / path).resolve()
        if root not in file.parents:
            raise HarnessError(f"{path} is outside the mission folder")
        try:
            src = preprocess(file, root)
        except (OSError, PreprocessError) as e:
            raise HarnessError(str(e)) from e
        if function:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", function):
                raise HarnessError(f"bad function name {function!r}")
            code = f"{function} = compile (_this # 0); true"
        else:
            effects = side_effects(src)
            if effects and not force:
                return {"ok": False, "error": "file has top-level statements besides function definitions; "
                        "reloading re-runs them. Pass force=true to reload anyway.", "side_effects": effects}
            code = "call compile (_this # 0); true"
        return self.exec(code, target, timeout=20, args=[src], strip=False)

    # -- observing -----------------------------------------------------------------------------

    def events(self, since: int | None = None, kinds: list[str] | None = None, types: list[str] | None = None,
               limit: int = 200, wait: float = 0) -> dict:
        b = self.bridge()
        since = b.cursor() if since is None else since
        res = b.events(since=since, wait=wait, limit=5000)
        evs = res.get("events", [])
        if kinds:
            evs = [e for e in evs if e.get("k") in kinds]
        if types:
            evs = [e for e in evs if e.get("type") in types]
        return {"next": res.get("next"), "dropped": res.get("dropped"), "count": len(evs),
                "events": evs[-limit:] if limit else evs}

    def wait_for(self, match: dict, since: int | None = None, timeout: float = 30) -> dict:
        b = self.bridge()
        pred = matcher(match)
        start = b.cursor() if since is None else since
        ev, nxt = b.wait_for(pred, start, timeout)
        return {"found": ev is not None, "event": ev, "next": nxt}

    def rpt(self, machine: str = "server", grep: str | None = None, tail: int = 100) -> dict:
        st = self._require()
        proc = next((p for p in st.procs if p.name == machine), None)
        if proc is None or not proc.profile:
            raise HarnessError(f"unknown machine {machine!r}; known: {[p.name for p in st.procs if p.profile]}")
        rpts = sorted(Path(proc.profile).glob("*.rpt"), key=lambda p: p.stat().st_mtime)
        if not rpts:
            return {"file": None, "lines": []}
        lines = rpts[-1].read_text("utf-8", "replace").splitlines()
        if grep:
            rx = re.compile(grep)
            lines = [line for line in lines if rx.search(line)]
        return {"file": str(rpts[-1]), "lines": lines[-tail:]}

    def snapshot(self, camera_pos: list | None = None, camera_target: list | None = None, fov: float = 0.75,
                 max_width: int = 1280, hide_hud: bool = False, target: str | None = None,
                 timeout: float = 15) -> dict:
        b = self.bridge()
        if target is None:
            renderers = [m for m in self.machines(b) if m.get("iface") and m.get("brmh_ext")]
            if not renderers:
                raise HarnessError("no rendering machine with the brmh extension (start one: arma_client)")
            target = f"owner:{renderers[-1]['owner']}"
        out = self.home.captures / f"snap_{time.strftime('%Y%m%d-%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.png"
        since = b.cursor()
        args = [str(out).replace("\\", "/"), camera_pos or [], camera_target or [], fov, max_width, hide_hud]
        queued = self.exec(_snippet("snapshot.sqf"), target, timeout=5, args=args, strip=False)
        first = (queued.get("results") or [{}])[0].get("r")
        if not queued.get("ok") or not first or first[1] != 0 or "queued" not in str(first[0]):
            raise HarnessError(f"capture not queued: {queued}")
        ev, _ = b.wait_for(lambda e: e.get("k") == "ext" and e.get("func") == "frame_done", since, timeout)
        if ev is None:
            raise HarnessError(f"no frame captured within {timeout}s (is the client window minimised?)")
        data = list(ev.get("data") or []) + ["false", "?", 0, 0, 0, -1][len(ev.get("data") or []):]
        ok, path, w, h, ms, luma = data[:6]
        if ok != "true":
            raise HarnessError(f"capture failed: {path}")
        out_info = {"path": str(out), "width": int(w), "height": int(h), "encode_ms": float(ms),
                    "mean_luma": float(luma), "target": target}
        if 0 <= float(luma) < 6:
            out_info["warning"] = ("frame is (nearly) black: loading screen, mission transition, or nothing "
                                   "rendered yet; check arma_gui_text and retry")
        return out_info

    def gui_text(self, target: str = "interface", text_only: bool = True) -> dict:
        return self.exec("[true, 300, _this # 0] call BRMH_fnc_guiText", target, args=[text_only])

    def map_svg(self, names: bool = True, grid: bool = True, contours: bool = True, trees: bool = False,
                heights: bool = True, simple_roads: bool = True) -> dict:
        """Terrain map (engine's ExportSVG) plus the named locations parsed from it."""
        b = self.bridge()
        world_res = b.exec("[worldName, worldSize]", "server", timeout=5)
        world, size = (world_res.get("results") or [{}])[0].get("r") or ["", 0]
        path = self.home.captures / f"map_{world}.svg"
        flags = [names, grid, contours, trees, heights, simple_roads]
        code = '"brmh" callExtension ["map:svg", [_this # 0] + (_this # 1)]'
        res = self.exec(code, "server", timeout=120, args=[str(path).replace("\\", "/"), flags], strip=False)
        r = (res.get("results") or [{}])[0].get("r") or []
        if not path.exists():
            raise HarnessError(f"map export failed: {res}")
        return {"path": str(path), "world": world, "world_size": size, "bytes": path.stat().st_size,
                "export": r, "locations": _svg_locations(path, size)}

    # -- conversation ----------------------------------------------------------------------------

    def observe(self) -> dict:
        """Install the chat (interface machines) and kill (server) observers. Idempotent; they are gone
        after a mission restart, so callers re-run this rather than track it."""
        return self.exec(_snippet("observe.sqf"), "all", timeout=5, strip=False)

    # Several agent sessions can listen at once, each under its own name ("Zeus, spawn me a car").
    # Each name has a registry file in sessions/listeners/, owned by the process that claimed it. Within a process,
    # the tools and a chat wake's thread both update it: _LISTENERS keeps each read-and-write whole, or one undoes
    # the other (a wake's own listen used to wipe the note that it was on, and status said it was off).

    def _listener_file(self, name: str) -> Path:
        return self.home.sessions / "listeners" / f"{name.lower()}.json"

    def _listener(self, name: str, state: dict | None = None) -> dict:
        path = self._listener_file(name)
        if state is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state), encoding="utf-8")
            return state
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def claim_name(self, name: str, force: bool = False) -> dict:
        """Register this process as the session answering to ``name``. Refused if another live process
        holds it (two sessions answering the same name would both act on every message)."""
        name = check_agent_name(name)
        with _LISTENERS:
            held = self._listener(name)
            pid = held.get("pid")
            if pid and pid != os.getpid() and procutil.alive(pid) and _listening(held) and not force:
                raise HarnessError(f"name {name!r} is taken by another live session (pid {pid}) that is listening; "
                                   "pick another name, or pass force=true if that session is gone")
            others = [x for x in self._listeners() if x["name"].lower() != name.lower()]
            state = {"name": name, "pid": os.getpid(), "claimed": time.time(), "since": None, "started": None,
                     "deadline": None, "finished": None,
                     "color": held.get("color") or _free_color(name, [x.get("color") for x in others])}
            if held.get("pid") == os.getpid():
                state.update({k: held.get(k) for k in ("since", "started", "deadline", "finished", "wake")})
            self._listener(name, state)
        return {"name": name, "color": state["color"], "others": [x["name"] for x in others]}

    def set_wake(self, name: str, via: str | None) -> None:
        """Record that ``name``'s messages wake its session (via a channel, or OpenCode), for listener_status."""
        with _LISTENERS:
            state = self._listener(name)
            if state.get("pid") == os.getpid():
                state["wake"] = via
                self._listener(name, state)

    def agent_color(self, name: str) -> list[float]:
        """The colour a claimed name keeps (distinct from the other sessions'), else the default pick."""
        return self._listener(name).get("color") or agent_color(name)

    def _listeners(self) -> list[dict]:
        folder = self.home.sessions / "listeners"
        out = []
        for f in sorted(folder.glob("*.json")) if folder.exists() else []:
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return [x for x in out if x.get("name")]

    def listen(self, name: str = "Claude", since: int | None = None, timeout: float = 25,
               ack: str | None = "thinking...") -> dict:
        """Block until a player types a chat message addressed to ``name`` ("zeus, ...", "@zeus ...",
        "hey zeus ...", any case) or to everyone ("everyone, ..."). Returns the message, the kills since
        ``since``, and the cursor to pass back next time so nothing said in between is missed. ``ack``
        is shown at once as a hint on the sender's machine, so players see the message landed while the
        reply is being worked out."""
        self.claim_name(name)
        obs = self.observe()
        if not obs.get("ok"):
            raise HarnessError(f"could not install observers: {obs}")
        b = self.bridge()
        start = b.cursor() if since is None else since
        with _LISTENERS:
            state = self._listener(name)
            state.update({"since": start, "started": time.time(), "deadline": time.time() + timeout,
                          "finished": None})
            self._listener(name, state)
        try:
            return self._listen(b, name, start, timeout, ack)
        finally:
            with _LISTENERS:
                state = self._listener(name)
                if state.get("pid") == os.getpid():
                    state["finished"] = time.time()
                    self._listener(name, state)

    def listener_status(self, b: Bridge) -> dict:
        """Deterministic answer to "is the listener on?": the chat observer per interface machine (it
        captures messages whether or not anyone listens) and, per named session, whether its process is
        alive, whether a listen call is waiting now, and messages to it since its last listen started."""
        obs = b.exec('not isNil "brmh_observeChatEh"', "interface", timeout=5)
        observers = {str(r.get("o")): r.get("r") for r in obs.get("results") or []}
        sessions = []
        for st in self._listeners():
            alive = procutil.alive(st.get("pid", 0))
            waiting = alive and st.get("started") is not None and st.get("finished") is None \
                and time.time() < (st.get("deadline") or 0)
            unread = []
            if st.get("since") is not None:
                rx = _address_rx(st["name"])
                evs = b.events(since=st["since"], limit=5000).get("events", [])
                unread = [e.get("text") for e in evs if e.get("type") == "chat" and rx.search(e.get("text") or "")]
            sessions.append({"name": st["name"], "session_alive": alive, "listen_call_waiting_now": waiting,
                             "chat_wake": (st.get("wake") or "off") if alive else "off",
                             "last_listen_since": st.get("since"), "messages_since_last_listen_started": unread[-5:]})
        return {
            "chat_observer_installed": observers or "no interface machine connected",
            "sessions": sessions,
            "meaning": "Chat is captured by the observer. A session hears it while its arma_listen call runs, or "
                       "all the time when its chat_wake is on: then each message to it starts its turn.",
        }

    def _listen(self, b: Bridge, name: str, start: int, timeout: float, ack: str | None) -> dict:
        rx = _address_rx(name).pattern
        is_chat = matcher({"k": "evt", "type": "chat", "text": {"$re": rx}})
        # A mission restart removes the observers: reinstall them once the player's machine is back
        # (its hello), and keep waiting.
        is_restart = matcher({"k": "mission", "state": "start"})
        is_back = matcher({"k": "hello", "iface": True})
        deadline = time.time() + timeout
        cursor, ev, restarted, first = start, None, False, True
        # Always look at least once: with timeout 0 the deadline has already passed, and that call is
        # meant to check what is waiting, not to skip the check.
        while ev is None and (first or time.time() < deadline):
            first = False
            hit, cursor = b.wait_for(lambda e, r=restarted: is_chat(e) or is_restart(e) or (r and is_back(e)),
                                     cursor, max(0.0, deadline - time.time()))
            if hit is None:
                break
            if is_restart(hit):
                restarted = True
            elif is_chat(hit):
                ev = hit
            else:
                restarted = False
                with contextlib.suppress(HarnessError, BridgeError):
                    self.observe()
        nxt = cursor
        if ev is not None and ack:
            with contextlib.suppress(HarnessError, BridgeError):
                self.exec(_ACK_SQF, f"owner:{ev.get('o')}", timeout=3,
                          args=[name, ack, _hex(self.agent_color(name))], strip=False)
        between = b.events(since=start, limit=5000).get("events", [])
        kills = [e for e in between if e.get("k") == "evt" and e.get("type") == "killed"
                 and (ev is None or e.get("seq", 0) < ev.get("seq", 0))]
        return {"found": ev is not None, "message": ev, "kills": kills, "next": nxt}

    def say(self, text: str, sender: str = "Claude", hint: bool = False, target: str = "interface") -> dict:
        """Show a chat line "<sender>: <text>" (own colour) to players; hint=true also shows a hint box."""
        sender = check_agent_name(sender)
        made = self.exec(_snippet("say_channel.sqf"), "server", timeout=5, args=[sender, self.agent_color(sender)],
                         strip=False)
        channel = (made.get("results") or [{}])[0].get("r")
        if not isinstance(channel, int | float):
            channel = 0
        return self.exec(_snippet("say.sqf"), target, timeout=5,
                         args=[text, sender, hint, int(channel), _hex(self.agent_color(sender))], strip=False)

    def view(self, radius: float = 300, max_objects: int = 40, target: str = "interface") -> dict:
        """What the player's camera sees, as data: player and world state plus on-screen buildings,
        vehicles and units with screen coordinates, positions and line-of-sight. Pair with a snapshot."""
        return self.exec(_snippet("view.sqf"), target, timeout=10, args=[radius, max_objects], strip=False)


def _observer_boot_item() -> dict:
    """Boot payload entry (runs at every mission start, on the server) that installs the chat and kill
    observers on every machine, including players who join later (remoteExec JIP queue). So chat is
    always captured, whether or not a listen call is waiting."""
    code = '[[], compile (_this # 0)] remoteExec ["call", 0, "brmh_observers"]; true'
    return {"code": code, "target": "server", "args": [_snippet("observe.sqf")], "label": "observers"}


_LISTENERS = threading.Lock()
# A name is someone's while they listen for it: a wake on, a listen call running, or one that ended within this long,
# the most a listen loop spends on one request between calls. After that a live process that stopped listening, such
# as an MCP server left idle in OpenCode's background service, no longer keeps the name from a new session.
NAME_IDLE_S = 600


def _listening(state: dict) -> bool:
    if state.get("wake"):
        return True
    last = max(state.get("finished") or 0, state.get("deadline") or 0, state.get("claimed") or 0)
    return time.time() - last < NAME_IDLE_S


_ACK_SQF = """hintSilent parseText format ["<t color='%3'>%1</t> %2", _this # 0, _this # 1, _this # 2]"""

# Chat colours for agent names (RGBA): "Claude" keeps the original orange, other names get a stable
# pick from the rest, so each agent's lines are told apart at a glance.
_PALETTE = [[0.95, 0.55, 0.15, 1], [0.35, 0.75, 1.0, 1], [0.55, 0.9, 0.35, 1], [0.95, 0.4, 0.75, 1],
            [1.0, 0.85, 0.25, 1], [0.7, 0.55, 1.0, 1], [0.3, 0.9, 0.8, 1], [1.0, 0.45, 0.4, 1]]


def check_agent_name(name: str) -> str:
    """Agent names are what players type ("Zeus, ..."): one word, letters first, at most 24 chars."""
    name = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,23}", name):
        raise HarnessError(f"bad agent name {name!r}: one word, starting with a letter (letters, digits, - _)")
    if name.lower() == "everyone":
        raise HarnessError("'everyone' is reserved: it addresses all listening sessions")
    return name


def agent_color(name: str) -> list[float]:
    if name.lower() == "claude":
        return _PALETTE[0]
    return _PALETTE[1 + sum(name.lower().encode()) % (len(_PALETTE) - 1)]


def _free_color(name: str, taken: list) -> list[float]:
    """The name's default colour if no other session uses it, else the first unused one."""
    want = agent_color(name)
    if want not in taken:
        return want
    return next((c for c in _PALETTE[1:] if c not in taken), want)


def _hex(rgba: list[float]) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgba[:3])


def _address_rx(name: str) -> re.Pattern:
    """A chat line addressed to ``name`` (or to everyone): "zeus, ...", "@zeus ...", "hey zeus ..."."""
    return re.compile(rf"(?i)^\s*(@|hey\s+|ok\s+)?({re.escape(name)}|everyone)\b")


def _compact_errors(errors: list[dict], keep: int = 10) -> list[dict]:
    """Collapse repeats of the same script error (an error inside a loop fires once per iteration and
    can run to megabytes): one entry per distinct error with a ``repeats`` count, first ``keep`` kept."""
    seen: dict[tuple, dict] = {}
    for e in errors:
        key = (e.get("file"), e.get("line"), e.get("pos"), e.get("text"))
        if key in seen:
            seen[key]["repeats"] = seen[key].get("repeats", 1) + 1
        else:
            seen[key] = dict(e)
    out = list(seen.values())
    if len(out) > keep:
        out = out[:keep] + [{"text": f"... {len(out) - keep} more distinct errors (see arma_errors)"}]
    return out


def _svg_locations(path: Path, world_size: float) -> list[dict]:
    """Named locations from an ExportSVG file, converted to world coordinates (SVG y is flipped)."""
    text = path.read_text("utf-8", "replace")
    out = []
    for m in re.finditer(r'<text[^>]*\bx="([\d.]+)"[^>]*\by="([\d.]+)"[^>]*>([^<]+)</text>', text):
        label = m.group(3).strip()
        if label and not label.isdigit() and not re.fullmatch(r"\d{3}", label):
            out.append({"name": label, "x": round(float(m.group(1))), "y": round(world_size - float(m.group(2)))})
    return out


def _server_cfg(mission_folder: str, password: str) -> str:
    return f"""// generated by arma-harness
hostname = "arma-harness";
password = "{password}";
passwordAdmin = "{secrets.token_hex(8)}";
loopback = 1;               // LAN mode: refuses non-local connections, stays off Steam's server list
BattlEye = 0;
verifySignatures = 0;
persistent = 1;             // required by -autoInit
kickDuplicate = 0;
allowedFilePatching = 0;
headlessClients[] = {{"127.0.0.1"}};
localClient[] = {{"127.0.0.1"}};
class Missions {{
	class Harness {{
		template = "{mission_folder}";
		difficulty = "Custom";
	}};
}};
"""
