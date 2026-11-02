"""BRMH in-game bridge: a localhost HTTP endpoint inside the Arma process (via Pythia).

Runs on the hub machine (the server, or the local host in SP / host-and-play). Python 3.10, stdlib only.

Activation is opt-in per process: the bridge starts only if the arma-harness host wrote
``<home>/sessions/<pid>.json`` for this game process. Without it every call is a cheap no-op, so a
player who merely loads the mod gets nothing. The bound port is written to ``<pid>.port.json``.

SQF side (BRMH_fnc_onFrame / BRMH_fnc_out) calls, through Pythia:
    brmh.bridge.start(mission, world) -> [active, port]
    brmh.bridge.poll()                -> [request_json, ...]   (never blocks)
    brmh.bridge.emit(envelope_json)   -> None

Host side (HTTP, header X-BRMH-Token):
    POST /exec    {code, target="server", timeout=10, scheduled=false, args=[]} -> collected results
    GET  /events  ?since=N&wait=S&limit=L                                       -> {next, events, dropped}
    GET  /status                                                                -> bridge state
"""
import collections
import hmac
import http.server
import json
import os
import sys
import threading
import time
import traceback

MAX_EVENTS = 50000
MAX_POLL = 64


def harness_home():
    override = os.environ.get("BRMH_HOME")
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "arma-harness")


def session_paths(pid=None):
    pid = pid or os.getpid()
    sessions = os.path.join(harness_home(), "sessions")
    return os.path.join(sessions, "%d.json" % pid), os.path.join(sessions, "%d.port.json" % pid)


class Slot:
    __slots__ = ("event", "expect", "results", "owners", "target", "created")

    def __init__(self, target):
        self.event = threading.Event()
        self.expect = None
        self.results = []
        self.owners = None
        self.target = target
        self.created = time.time()


class Hub:
    """All bridge state. One instance per process, kept on ``sys`` so it survives Pythia reloads."""

    def __init__(self):
        self.lock = threading.Lock()
        self.changed = threading.Condition(self.lock)
        self.server = None
        self.port = 0
        self.token = None
        self.session = {}
        self.inbox = collections.deque()
        self.pending = {}
        self.events = collections.deque(maxlen=MAX_EVENTS)
        self.next_seq = 0
        self.next_id = 0
        self.epoch = 0
        self.mission = None
        self.started = None
        self.polls = 0

    # -- game side --------------------------------------------------------------------------

    def start(self, mission="", world=""):
        with self.lock:
            if self.server is not None:
                # The game only calls start() once per mission (preInit resets its flag), so a call
                # while running means the mission (re)started, even under the same name.
                self._new_epoch(mission, world)
                return [True, self.port]
        session_file, port_file = session_paths()
        if not os.path.isfile(session_file):
            return [False, 0]
        with open(session_file, encoding="utf-8") as f:
            session = json.load(f)
        token = session.get("token")
        if not token:
            return [False, 0]
        server = http.server.ThreadingHTTPServer(("127.0.0.1", int(session.get("port", 0))), _make_handler(self))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, name="brmh-http", daemon=True).start()
        with self.lock:
            self.server = server
            self.port = server.server_address[1]
            self.token = token
            self.session = session
            self.started = time.time()
            self._new_epoch(mission, world)
        tmp = port_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "port": self.port, "started": self.started}, f)
        os.replace(tmp, port_file)
        return [True, self.port]

    def _new_epoch(self, mission, world):
        """A (re)started mission: fail requests of the old run and queue the boot payload again."""
        self.epoch += 1
        self.mission = (mission, world)
        for rid, slot in list(self.pending.items()):
            if slot.expect is None or len(slot.results) < slot.expect:
                slot.results.append({"id": rid, "ok": False, "error": "mission restarted"})
                slot.event.set()
        self.inbox.clear()
        for i, item in enumerate(self.session.get("boot", [])):
            self.inbox.append(json.dumps({
                "id": "boot%d.%d" % (self.epoch, i),
                "code": item.get("code", ""),
                "target": item.get("target", "server"),
                "scheduled": bool(item.get("scheduled", False)),
                "args": item.get("args", []),
            }))
        self._append({"k": "mission", "state": "start", "epoch": self.epoch, "mission": mission, "world": world})

    def poll(self):
        with self.lock:
            self.polls += 1
            out = []
            while self.inbox and len(out) < MAX_POLL:
                out.append(self.inbox.popleft())
            return out

    def emit(self, envelope_json):
        try:
            env = json.loads(envelope_json)
        except ValueError:
            env = {"k": "bad", "raw": envelope_json[:500]}
        if not isinstance(env, dict):
            env = {"k": "bad", "raw": envelope_json[:500]}
        with self.lock:
            kind = env.get("k")
            slot = self.pending.get(env.get("id")) if kind in ("dispatch", "res") else None
            if slot is not None:
                if kind == "dispatch":
                    slot.owners = env.get("owners") or []
                    slot.expect = len(slot.owners)
                else:
                    slot.results.append(env)
                if slot.expect is not None and len(slot.results) >= slot.expect:
                    slot.event.set()
            self._append(env)

    def _append(self, env):
        env["seq"] = self.next_seq
        env["epoch"] = self.epoch
        self.next_seq += 1
        self.events.append(env)
        self.changed.notify_all()

    # -- host side ----------------------------------------------------------------------------

    def submit(self, req):
        with self.lock:
            self.next_id += 1
            rid = "q%d" % self.next_id
            slot = Slot(req.get("target", "server"))
            self.pending[rid] = slot
            self.inbox.append(json.dumps({
                "id": rid,
                "code": req.get("code", ""),
                "target": slot.target,
                "scheduled": bool(req.get("scheduled", False)),
                "args": req.get("args", []),
            }))
        return rid, slot

    def collect(self, rid, slot, timeout):
        done = slot.event.wait(timeout)
        with self.lock:
            self.pending.pop(rid, None)
            results = list(slot.results)
        ok = done and bool(results) and all(r.get("ok") for r in results)
        out = {"id": rid, "ok": ok, "target": slot.target, "owners": slot.owners, "results": results,
               "ms": round((time.time() - slot.created) * 1000, 1)}
        if not done:
            out["error"] = "timeout" if slot.owners is not None else "timeout (never dispatched: bridge not polled?)"
        elif slot.expect == 0:
            out["error"] = "no machine matches target %r" % slot.target
        return out

    def read_events(self, since, wait, limit):
        deadline = time.time() + max(0.0, wait)
        with self.lock:
            while self.next_seq <= since and time.time() < deadline:
                self.changed.wait(max(0.0, deadline - time.time()))
            oldest = self.events[0]["seq"] if self.events else self.next_seq
            evs = [e for e in self.events if e["seq"] >= since]
            return {"next": self.next_seq, "events": evs[:limit], "dropped": since < oldest,
                    "more": len(evs) > limit}

    def status(self):
        with self.lock:
            return {"active": self.server is not None, "port": self.port, "pid": os.getpid(),
                    "epoch": self.epoch, "mission": self.mission, "pending": len(self.pending),
                    "queued": len(self.inbox), "next": self.next_seq, "polls": self.polls,
                    "uptime": round(time.time() - self.started, 1) if self.started else 0,
                    "python": sys.version.split()[0]}

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def _make_handler(hub):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorised(self):
            given = self.headers.get("X-BRMH-Token", "")
            if hub.token and hmac.compare_digest(given.encode(), hub.token.encode()):
                return True
            self._send(403, {"error": "bad token"})
            return False

        def _query(self):
            out = {}
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        out[k] = v
            return out

        def do_GET(self):
            if not self._authorised():
                return
            try:
                if self.path.startswith("/status"):
                    self._send(200, hub.status())
                elif self.path.startswith("/events"):
                    q = self._query()
                    self._send(200, hub.read_events(int(q.get("since", 0)), float(q.get("wait", 0)),
                                                    int(q.get("limit", 1000))))
                else:
                    self._send(404, {"error": "unknown path"})
            except Exception:
                self._send(500, {"error": traceback.format_exc()[-1500:]})

        def do_POST(self):
            if not self._authorised():
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(length) or b"{}")
                if self.path.startswith("/exec"):
                    rid, slot = hub.submit(req)
                    res = hub.collect(rid, slot, float(req.get("timeout", 10)))
                    self._send(200 if "error" not in res else 504, res)
                else:
                    self._send(404, {"error": "unknown path"})
            except Exception:
                self._send(500, {"error": traceback.format_exc()[-1500:]})

    return Handler


def _hub():
    hub = getattr(sys, "_brmh_hub", None)
    if hub is None:
        hub = sys._brmh_hub = Hub()
    return hub


# -- Pythia entry points: must never raise into the game (Pythia shows errors in systemChat) --

def start(mission="", world=""):
    try:
        return _hub().start(mission, world)
    except Exception:
        _log_error()
        return [False, 0]


def poll():
    try:
        return _hub().poll()
    except Exception:
        _log_error()
        return []


def emit(envelope_json):
    try:
        _hub().emit(envelope_json)
    except Exception:
        _log_error()


def _log_error():
    try:
        path = os.path.join(harness_home(), "logs", "bridge-%d.log" % os.getpid())
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), traceback.format_exc()))
    except Exception:
        pass
