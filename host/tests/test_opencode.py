"""OpenCode as the commander's client: its workspace's lockdown, and wakes sent into its session."""
import io
import json
import subprocess
import time
import urllib.error

import pytest

from arma_harness.commander import opencode
from arma_harness.commander.server import TOOL_NAMES, Server


class FakeService:
    """OpenCode's server: sessions with their folders, which of them are running, and every prompt posted."""

    def __init__(self, sessions: dict[str, str], active: list[str]):
        self.sessions, self.active = sessions, active
        self.prompts: list[tuple[str, dict]] = []
        self.refuse: int | None = None

    def call(self, method, path, body=None):
        if path == "/api/session/active":
            return {"data": {sid: {"type": "running"} for sid in self.active}}
        sid = path.split("/")[3]
        if method == "GET":
            return {"data": {"id": sid, "location": {"directory": self.sessions[sid]}}}
        if self.refuse:
            code, self.refuse = self.refuse, None
            raise urllib.error.HTTPError(path, code, "no", {}, io.BytesIO(b"{}"))
        self.prompts.append((sid, body))
        return {"data": {}}


def wakes(service, workspace=r"C:\cmd\workspace-opencode"):
    log = []
    route = opencode.Wakes(service, workspace, log.append)
    route.RETRY_S = 0.01
    return route, log


def settle(route):
    deadline = time.time() + 2
    while route.queue.unfinished_tasks and not route.queue.empty() and time.time() < deadline:
        time.sleep(0.01)
    time.sleep(0.05)


def test_the_lockdown_denies_everything_but_the_commanders_tools():
    config = opencode.workspace_config(["py", "-m", "x"], "oc.exe", opencode.Path("C:/w"), "commander")
    rules = config["agents"]["commander"]["permissions"]
    assert config["permissions"] == rules
    assert rules[0] == {"action": "*", "resource": "*", "effect": "deny"}  # the last match wins, so this goes first
    assert rules[-1] == {"action": "commander_*", "resource": "*", "effect": "allow"}
    assert config["default_agent"] == "commander"
    assert config["agents"]["build"] == config["agents"]["plan"] == {"disabled": True}
    server = config["mcp"]["servers"]["commander"]
    assert server["codemode"] is False  # code mode would hide the tools behind a JavaScript runner
    assert server["environment"][opencode.CLIENT_ENV] == "opencode"
    assert config["warming"] is False


def test_every_commander_tool_is_named_so_the_allow_rule_matches():
    assert all(name.startswith("commander_") for name in TOOL_NAMES)


def test_wakes_go_to_the_session_running_in_the_workspace():
    service = FakeService({"ses_a": "C:/other", "ses_b": "c:\\CMD\\workspace-opencode\\"}, ["ses_a", "ses_b"])
    route, log = wakes(service)
    route.tool_called()
    assert route.session == "ses_b"
    service.active = []  # between turns nothing runs, and the session is already known
    route.send("09:30 | turn 2 | woke on: 1 message", {"turn": "2", "woke_on": "1 message"})
    settle(route)
    sid, body = service.prompts[0]
    assert sid == "ses_b"
    assert body["delivery"] == "queue"
    assert body["text"].startswith('<channel source="commander" turn="2" woke_on="1 message">\n09:30 | turn 2')
    assert body["text"].endswith("</channel>")


def test_a_wake_in_deliver_mode_steers_into_the_turn():
    service = FakeService({"ses_b": r"C:\cmd\workspace-opencode"}, ["ses_b"])
    route, _ = wakes(service)
    route.send("x", {}, steer=True)
    settle(route)
    assert service.prompts[0][1]["delivery"] == "steer"


def test_wakes_keep_their_order_and_wait_for_the_session():
    service = FakeService({"ses_b": r"C:\cmd\workspace-opencode"}, [])
    route, _ = wakes(service)
    for n in range(3):
        route.send(str(n), {})
    time.sleep(0.05)
    assert service.prompts == []
    service.active = ["ses_b"]
    settle(route)
    assert [body["text"].split("\n")[1] for _, body in service.prompts] == ["0", "1", "2"]


def test_a_closed_session_is_looked_up_again():
    service = FakeService({"ses_b": r"C:\cmd\workspace-opencode", "ses_c": r"C:\cmd\workspace-opencode"}, ["ses_b"])
    route, log = wakes(service)
    route.tool_called()
    service.refuse, service.active = 404, ["ses_c"]
    route.send("x", {})
    settle(route)
    assert service.prompts[0][0] == "ses_c"
    assert any("refused (404)" in line for line in log)


def test_two_sessions_in_the_workspace_are_reported_not_guessed():
    service = FakeService({"ses_b": r"C:\cmd\workspace-opencode", "ses_c": r"C:\cmd\workspace-opencode"},
                          ["ses_b", "ses_c"])
    route, log = wakes(service)
    route.tool_called()
    assert route.session is None
    assert "2 sessions" in log[0]


def test_the_server_sends_wakes_by_the_route_and_not_as_a_channel():
    class Route:
        def __init__(self):
            self.sent, self.calls = [], 0

        def send(self, text, meta, steer=False):
            self.sent.append((text, meta, steer))

        def tool_called(self):
            self.calls += 1

    stdout, route = io.BytesIO(), Route()
    server = Server(stdin=io.BytesIO(), stdout=stdout, route=route)
    server.wake("briefing", {"turn": "1"})
    assert route.sent == [("briefing", {"turn": "1"}, False)]
    assert stdout.getvalue() == b""
    server._tool({"id": 1, "params": {"name": "nope"}})
    assert route.calls == 1


def test_the_service_is_found_by_its_status_command(tmp_path):
    def run(command, **kwargs):
        assert command[1:] == ["service", "status"]
        return subprocess.CompletedProcess(command, 0, "http://127.0.0.1:28894\n", "")

    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    (tmp_path / ".config" / "opencode" / "service.json").write_text(json.dumps({"password": "pw"}))
    service = opencode.Service("oc", run=run, home=tmp_path)
    assert service._find() == "http://127.0.0.1:28894"
    assert service._auth() == {"Authorization": "Basic b3BlbmNvZGU6cHc="}  # opencode:pw


def test_the_newest_desktop_copy_is_used(tmp_path, monkeypatch):
    for version in ("2.2.7-x64", "2.10.1-x64", "2.9.0-x64"):
        (tmp_path / "ai.opencode.desktop" / "cli" / version).mkdir(parents=True)
        (tmp_path / "ai.opencode.desktop" / "cli" / version / "opencode-cli.exe").write_text("")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv(opencode.CLI_ENV, raising=False)
    monkeypatch.setattr(opencode.shutil, "which", lambda name: None)
    assert "2.10.1-x64" in opencode.find_cli()


@pytest.mark.parametrize("named", ["C:/oc/opencode.exe"])
def test_a_named_command_line_wins(monkeypatch, named):
    monkeypatch.setenv(opencode.CLI_ENV, named)
    assert opencode.find_cli() == named


def test_a_new_battle_restarts_the_workspaces_server():
    calls = []

    class Service:
        def call(self, method, path, body=None):
            calls.append((method, path))
            return {}

    assert opencode.restart_server(Service(), opencode.Path(r"C:\w s"), "commander") == "restarted"
    assert calls == [("POST", "/api/experimental/mcp/commander/disconnect?location[directory]=C%3A%5Cw%20s"),
                     ("POST", "/api/experimental/mcp/commander/connect?location[directory]=C%3A%5Cw%20s")]


def test_no_opencode_server_running_is_said_not_raised():
    class Service:
        def call(self, method, path, body=None):
            raise OSError("OpenCode's background server isn't running")

    assert opencode.restart_server(Service(), opencode.Path("C:/w"), "commander").startswith("not restarted")
