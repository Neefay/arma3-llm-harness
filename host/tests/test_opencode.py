"""OpenCode as the commander's client: its workspace's lockdown, and wakes sent into its session."""
import io
import json
import subprocess
import time
import urllib.error
from pathlib import Path

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


# -- the lockdown, checked through OpenCode's own permission evaluation ------------------------------------------------

class Permissions:
    """OpenCode answering permission checks: everything denied but what's in ``allowed``."""

    def __init__(self, allowed=("commander_commander_order",)):
        self.allowed, self.calls = set(allowed), []

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/api/session":
            return {"data": {"id": "ses_check"}}
        if method == "DELETE":
            return {}
        return {"data": {"id": "per_1", "effect": "allow" if body["action"] in self.allowed else "deny"}}


def test_policies_back_the_lockdown_up():
    """The desktop app gives its sessions the browser, in rules after the workspace's: only a policy stops that."""
    config = opencode.workspace_config(["py"], "oc.exe", opencode.Path("C:/w"), "commander")
    assert config["policies"] == [{"action": "tool.use", "resource": "*", "effect": "deny"},
                                  {"action": "tool.use", "resource": "commander_*", "effect": "allow"}]


def test_the_lockdown_holds_when_only_the_commanders_tools_are_allowed():
    assert opencode.check_lockdown(Permissions(), "ses_a", "commander") == {
        "ok": True, "allowed_outside": [], "commander_tools_allowed": True}


def test_a_tool_left_open_fails_the_lockdown():
    result = opencode.check_lockdown(Permissions({"commander_commander_order", "browser"}), "ses_a", "commander")
    assert not result["ok"]
    assert result["allowed_outside"] == ["browser:*"]


def test_the_commanders_own_tools_denied_fails_it_too():
    assert not opencode.check_lockdown(Permissions(set()), "ses_a", "commander")["ok"]


def test_the_probes_cover_every_built_in_and_the_arma_server():
    probed = {action for action, _ in opencode.DENIED}
    assert {"read", "edit", "shell", "webfetch", "websearch", "subagent", "skill", "execute", "browser",
            "question", "arma_arma_exec"} <= probed


def test_the_lockdown_check_uses_a_throwaway_session_and_deletes_it(tmp_path, monkeypatch):
    from arma_harness.commander import operator
    from arma_harness.config import Home

    monkeypatch.setenv(opencode.CLI_ENV, "oc.exe")
    service = Permissions()
    result = operator.check_opencode_lockdown(Home(tmp_path), service)
    assert result["ok"]
    create = service.calls[0]
    assert create[:2] == ("POST", "/api/session") and create[2]["agent"] == "commander"
    assert create[2]["location"]["directory"].endswith("workspace-opencode")
    assert service.calls[-1][:2] == ("DELETE", "/api/session/ses_check")


def test_the_session_is_reported_once_found():
    service = FakeService({"ses_b": r"C:\cmd\workspace-opencode"}, ["ses_b"])
    found = []
    route = opencode.Wakes(service, r"C:\cmd\workspace-opencode", [].append, found.append)
    route.tool_called()
    route.tool_called()
    time.sleep(0.1)
    assert found == ["ses_b"]


# -- the review, from an OpenCode session -----------------------------------------------------------------------------

def opencode_messages():
    def assistant(t, parts, output=10):
        return {"type": "assistant", "time": {"created": t * 1000},
                "model": {"id": "gpt-6-luna", "providerID": "openai"},
                "tokens": {"input": 100, "output": output, "reasoning": 2, "cache": {"read": 1000, "write": 0}},
                "content": parts}

    def tool(name, given=None):
        return {"type": "tool", "name": f"commander_commander_{name}", "state": {"input": given or {}}}

    return [
        {"type": "user", "text": "start"},
        assistant(100, [tool("mission")]),
        assistant(103, [tool("order", {"to": "Alpha"}), {"type": "text", "text": "Alpha moving."}]),
        assistant(105, [tool("end_turn")]),
        {"type": "user", "text": '<channel source="commander" turn="2" woke_on="1 message">\nT+00:09 | turn 2'},
        assistant(110, [{"type": "reasoning", "text": ""}, {"type": "tool", "name": "browser_open", "state": {}},
                        tool("end_turn")], output=5),
        {"type": "user", "text": "how did it go?"},
        assistant(400, [{"type": "text", "text": "Well."}]),  # a chat with the operator afterwards: not the battle
    ]


def test_the_review_reads_an_opencode_session():
    from arma_harness.commander import aar

    session = aar._read_opencode(opencode_messages(), [(0.0, 1), (9.8, 2)])
    assert session["model"] == "gpt-6-luna"
    assert session["requests"] == 4  # the chat afterwards is left out
    assert session["output_tokens"] == 35 and session["reasoning_tokens"] == 8
    assert session["peak_context"] == 1100
    assert session["tool_calls"] == 4
    assert session["turns"][1]["actions"] == [{"t": 3.0, "tool": "order", "input": {"to": "Alpha"}}]
    assert session["turns"][1]["said"] == [{"t": 3.0, "text": "Alpha moving."}]
    assert 2 in session["turns"]
    assert session["outside_lockdown_used"] == {"browser_open": 1}


def battle_folder(tmp_path, lockdown):
    folder = tmp_path / "run" / "commander-1" / "west"
    folder.mkdir(parents=True)
    (folder.parent / "battle.json").write_text("{}")
    (folder / "state.json").write_text("{}")
    (folder / "turns.jsonl").write_text(json.dumps({"turn": 1, "start": 0.0}) + "\n")
    (folder / "client.json").write_text(json.dumps({"client": "opencode", "session": "ses_b", "lockdown": lockdown}))
    return folder


def test_the_review_keeps_the_export_and_falls_back_to_it(tmp_path):
    from arma_harness.commander import aar

    folder = battle_folder(tmp_path, {"ok": True, "allowed_outside": []})
    info = json.loads((folder / "client.json").read_text())

    class Export:
        def call(self, method, path, body=None):
            assert path == "/api/experimental/session/ses_b/export"
            return {"data": {"messages": opencode_messages()}}

    class Gone:
        def call(self, method, path, body=None):
            raise OSError("OpenCode isn't running")

    first = aar.opencode_session(folder, info, Export())
    assert (folder / aar.OPENCODE_EXPORT).exists()
    assert aar.opencode_session(folder, info, Gone()) == first
    assert first["tools_outside_lockdown"] == []


def test_a_failed_lockdown_shows_in_the_review(tmp_path):
    from arma_harness.commander import aar

    folder = battle_folder(tmp_path, {"ok": False, "allowed_outside": ["browser:*"]})
    (folder / aar.OPENCODE_EXPORT).write_text(json.dumps({"messages": opencode_messages()}))

    class Gone:
        def call(self, method, path, body=None):
            raise OSError("no")

    session = aar.opencode_session(folder, json.loads((folder / "client.json").read_text()), Gone())
    assert session["tools_outside_lockdown"] == ["browser:*"]


def test_the_app_shows_a_wake_as_radio_traffic_and_the_model_gets_the_block():
    service = FakeService({"ses_b": r"C:\cmd\workspace-opencode"}, ["ses_b"])
    route, _ = wakes(service)
    briefing = "T+01:40 | turn 3 | woke on: 1 message\n\nTRAFFIC\n[01:37] Alpha: Arrived."
    route.send(briefing, {"turn": "3"})
    settle(route)
    body = service.prompts[0][1]
    assert body["text"].startswith('<channel source="commander" turn="3">\nT+01:40 | turn 3')
    # the app reads displayText only with comments and attachments beside it, as its own prompts have
    assert body["metadata"] == {"displayText": opencode.display_text(briefing), "comments": [], "attachments": []}


def test_the_display_lays_every_section_out():
    briefing = "\n".join([
        "T+15:02 | turn 23 | woke on: notice, 1 timer", "",
        "OBJECTIVES, 03:20 left", "Done: Take the hill.", "Hold it.", "",
        "NOTICE", "MISSION END. Time limit reached.", "",
        "NET", "Hammer  last heard 2 min ago", "",
        "TRAFFIC", "[01:37] Alpha: Arrived, grid 034 030.", "",
        "OVERDUE", "Bravo: missed 2 scheduled check-ins.", "",
        "VEHICLES", "V1  Mk6 Mortar  grid 020 020  as briefed", "",
        "YOUR NOTES", "First line.", "", "NET is a word here, not a heading.",
    ])
    # Plain text: the app shows user messages without Markdown, keeping line breaks and spaces.
    assert opencode.display_text(briefing).split("\n") == [
        "📻 RADIO  ·  TURN 23  ·  ⏱️ T+15:02", "📢  Woke on notice, 1 timer", opencode.RULE, "",
        "🎯 OBJECTIVES  ·  ⏳ 03:20 left", "✅  Take the hill.  (done)", "▫️  Hold it.", "",
        "📢 NOTICE", "🏁  MISSION END. Time limit reached.", "",
        "📶 NET", "•  Hammer — last heard 2 min ago", "",
        "💬 TRAFFIC", "01:37  ▸  Alpha: Arrived, grid 034 030.", "",
        "❗ OVERDUE", "•  Bravo: missed 2 scheduled check-ins.", "",
        "🚙 VEHICLES", "•  V1 — Mk6 Mortar · grid 020 020 · as briefed", "",
        "📝 YOUR NOTES", "┃ First line.", "┃", "┃ NET is a word here, not a heading.",
    ]
    assert not any(mark in opencode.display_text(briefing) for mark in ("**", "`", "###"))


def test_every_heading_the_briefing_writes_has_a_mark():
    import re

    from arma_harness.commander import runtime

    source = Path(runtime.__file__).read_text(encoding="utf-8")
    written = set(re.findall(r'"([A-Z][A-Z ]+[A-Z])"\]', source)) | {"OBJECTIVE"}
    written -= {"MISSION END"}
    assert written <= {name for name, _ in opencode.SECTIONS}, written - {name for name, _ in opencode.SECTIONS}


def test_a_briefing_in_another_shape_still_gets_a_header():
    assert opencode.display_text("MISSION END").startswith("📻 RADIO  ·  MISSION END")
