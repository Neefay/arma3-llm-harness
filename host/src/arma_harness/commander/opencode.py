"""OpenCode as the commander's client: its workspace, and wakes sent into its session through OpenCode's own server.

Claude Code wakes the commander with a channel notification on the MCP connection. OpenCode has nothing like it, but
its background server takes a prompt into a session from outside and starts a turn with it, or queues it behind the
turn already running (POST /api/session/{id}/prompt). This needs OpenCode 2 and its background server, which the
desktop app and the CLI both start.

The session isn't known in advance: it's whichever one, open in the commander's workspace, is running when a commander
tool is called. Its first call is in the turn the operator starts by typing "start".
"""
from __future__ import annotations

import base64
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

CLIENT_ENV = "BRMH_COMMANDER_CLIENT"
CLI_ENV = "BRMH_OPENCODE_CLI"
WORKSPACE_ENV = "BRMH_COMMANDER_WORKSPACE"
AGENT = "commander"
SYSTEM = ("You are the commander in a battle, and you command only by radio, through your commander tools. Your "
          "instructions are in the commander server's instructions and in what commander_mission returns.")


def find_cli() -> str | None:
    """OpenCode's command line: the one named in BRMH_OPENCODE_CLI, else on the PATH, else the desktop app's own."""
    if os.environ.get(CLI_ENV):
        return os.environ[CLI_ENV]
    for name in ("opencode", "opencode-cli"):
        if found := shutil.which(name):
            return found
    desktop = Path(os.environ.get("APPDATA", "")) / "ai.opencode.desktop" / "cli"

    def version(path: Path) -> tuple[int, ...]:
        numbers = path.parent.name.split("-")[0].split(".")
        return tuple(int(n) for n in numbers if n.isdigit())

    copies = sorted(desktop.glob("*/opencode-cli*"), key=version)
    return str(copies[-1]) if copies else None


def workspace_config(server_command: list[str], cli: str, workspace: Path, server_name: str) -> dict:
    """The workspace's opencode.json: the commander's server and agent, and every other tool denied.

    Permissions are matched last rule first, so "deny everything" followed by "allow this server's tools" leaves only
    those. But a session can carry rules of its own, after these: the desktop app gives each of its sessions its
    browser. Policies are applied after every rule and can only take access away, so the same two statements there
    are what really hold. The built-in primary agents are switched off too, so the session can't be moved to one with
    every tool.
    """
    lockdown = [{"action": "*", "resource": "*", "effect": "deny"},
                {"action": f"{server_name}_*", "resource": "*", "effect": "allow"}]
    return {
        "default_agent": AGENT,
        "permissions": lockdown,
        "policies": [{"action": "tool.use", "resource": "*", "effect": "deny"},
                     {"action": "tool.use", "resource": f"{server_name}_*", "effect": "allow"}],
        "agents": {
            AGENT: {"mode": "primary", "description": "Commands the battle by radio.", "system": SYSTEM,
                    "permissions": lockdown},
            "build": {"disabled": True},
            "plan": {"disabled": True},
        },
        "mcp": {"servers": {server_name: {
            "type": "local", "command": server_command, "codemode": False,
            "environment": {CLIENT_ENV: "opencode", CLI_ENV: cli, WORKSPACE_ENV: str(workspace)},
        }}},
        "websearch": False,
        "warming": False,  # it keeps the prompt cache warm with real, billed requests
        "snapshots": False,
    }


# Every built-in tool's permission, as OpenCode's docs name them, and another MCP server's tool: the commander may use
# none of them. The arma server's in particular would show it the whole battle.
DENIED = [("read", "C:/x.txt"), ("edit", "C:/x.txt"), ("glob", "*"), ("grep", "x"), ("shell", "dir"),
          ("subagent", "general"), ("skill", "*"), ("skill", "browser"), ("question", "*"), ("webfetch", "https://x"),
          ("websearch", "x"), ("experimental_image_generate", "*"), ("external_directory", "C:/x"), ("execute", "*"),
          ("opencode_list_mcp_resources", "*"), ("opencode_read_mcp_resource", "*"), ("browser", "*"),
          ("todowrite", "*"), ("arma_arma_exec", "*")]


def check_lockdown(service: Service, session: str, server_name: str) -> dict:
    """Ask OpenCode what this session may do, without a model call: every probe in DENIED must be denied, and the
    commander's own tools allowed. "ask" counts as allowed, since someone could say yes."""
    def effect(action: str, resource: str) -> str:
        body = {"action": action, "resources": [resource], "agent": AGENT}
        return service.call("POST", f"/api/session/{session}/permission", body)["data"]["effect"]

    allowed = [f"{action}:{resource}" for action, resource in DENIED if effect(action, resource) != "deny"]
    own = effect(f"{server_name}_commander_order", "*") == "allow"
    return {"ok": not allowed and own, "allowed_outside": allowed, "commander_tools_allowed": own}


def _same_folder(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class Service:
    """OpenCode's background server, found through its command line and signed in to with its password."""

    def __init__(self, cli: str, run: Callable = subprocess.run, home: Path | None = None):
        self.cli, self.run, self.home = cli, run, home or Path.home()
        self.url: str | None = None

    def _find(self) -> str:
        out = self.run([self.cli, "service", "status"], capture_output=True, text=True, timeout=30)
        urls = [word for word in out.stdout.split() if word.startswith("http")]
        if out.returncode or not urls:
            raise OSError(f"OpenCode's background server isn't running: {(out.stderr or out.stdout).strip()}")
        return urls[0].rstrip("/")

    def _auth(self) -> dict:
        path = self.home / ".config" / "opencode" / "service.json"
        if not path.exists():
            return {}
        password = json.loads(path.read_text(encoding="utf-8")).get("password", "")
        return {"Authorization": "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()}

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        for attempt in (1, 2):  # its port changes when it restarts
            if self.url is None:
                self.url = self._find()
            data = json.dumps(body).encode() if body is not None else None
            request = urllib.request.Request(self.url + path, data=data, method=method,
                                             headers={"Content-Type": "application/json", **self._auth()})
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read() or b"{}")
            except urllib.error.HTTPError:
                raise
            except OSError:
                self.url = None
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")


def restart_server(service: Service, workspace: Path, name: str) -> str:
    """Start the workspace's commander server afresh, for a new battle.

    OpenCode keeps one server process per folder, across sessions, where Claude Code starts one per session: left
    alone, the last battle's server would go on serving that battle to the new session."""
    where = "?location[directory]=" + urllib.parse.quote(str(workspace))
    try:
        service.call("POST", f"/api/experimental/mcp/{name}/disconnect{where}", {})
        service.call("POST", f"/api/experimental/mcp/{name}/connect{where}", {})
    except Exception as exc:
        return f"not restarted ({exc}): if a session was open there, close OpenCode before starting the battle"
    return "restarted"


class Wakes:
    """Sends each wake into the commander's session, in order, on a thread of its own so the battle never waits."""

    RETRY_S = 5.0
    TRIES = 12

    def __init__(self, service: Service, workspace: str, log: Callable[[str], None],
                 found: Callable[[str], None] | None = None):
        """``found`` is told the session once it's known."""
        self.service, self.workspace, self.log, self.found = service, workspace, log, found
        self.session: str | None = None
        self.queue: queue.Queue = queue.Queue()
        threading.Thread(target=self._work, daemon=True).start()

    def find_session(self) -> str | None:
        """The session running in the commander's workspace, if there's exactly one."""
        active = self.service.call("GET", "/api/session/active").get("data") or {}
        ours = []
        for session_id in active:
            info = self.service.call("GET", f"/api/session/{session_id}").get("data") or {}
            if _same_folder((info.get("location") or {}).get("directory", ""), self.workspace):
                ours.append(session_id)
        if len(ours) > 1:
            self.log(f"OpenCode: {len(ours)} sessions are running in the commander's workspace, {ours}, and wakes "
                     "can only go to one. Close the others.")
        return ours[0] if len(ours) == 1 else None

    def tool_called(self) -> None:
        """A commander tool was called, so its session is running now: the moment to learn which it is."""
        if self.session is not None:
            return
        try:
            self.session = self.find_session()
        except Exception as exc:  # the wake loop tries again; a tool call mustn't fail over this
            self.log(f"OpenCode: couldn't look up the commander's session: {exc}")
        if self.session:
            self.log(f"OpenCode: wakes go to session {self.session}")
            if self.found is not None:  # a score of requests to OpenCode: the commander's tool call shouldn't wait
                threading.Thread(target=self.found, args=(self.session,), daemon=True).start()

    def send(self, text: str, meta: dict, steer: bool = False) -> None:
        attributes = "".join(f' {key}="{value}"' for key, value in meta.items())
        self.queue.put({"text": f'<channel source="commander"{attributes}>\n{text}\n</channel>',
                        "delivery": "steer" if steer else "queue"})

    def _work(self) -> None:
        while True:
            body = self.queue.get()
            for _ in range(self.TRIES):
                if self._post(body):
                    break
                time.sleep(self.RETRY_S)
            else:
                self.log(f"OpenCode: a wake was never delivered:\n{body['text']}")

    def _post(self, body: dict) -> bool:
        try:
            if self.session is None:
                self.session = self.find_session()
                if self.session is None:
                    return False
            self.service.call("POST", f"/api/session/{self.session}/prompt", body)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:  # the session was closed or deleted: look for the one running now
                self.session = None
            self.log(f"OpenCode: a wake was refused ({exc.code}): {exc.read()[:300]!r}")
        except Exception as exc:
            self.log(f"OpenCode: a wake couldn't be sent: {exc}")
        return False
