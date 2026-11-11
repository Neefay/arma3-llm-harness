"""Chat that wakes the assistant: the watcher, what it says, and the arma server's side of a Claude Code channel."""
import json
import os
import subprocess
import sys
import threading
import time

import pytest

from arma_harness import chatwake


def test_a_wake_says_who_said_what_and_what_to_do():
    text, meta, display = chatwake.wake_text(
        {"name": "Nife", "text": "zeus, spawn a Hunter next to me", "seq": 42},
        [{"victim": "Rifleman", "killer": "Nife", "weapon": "MX", "distance": 120}], "Zeus")
    assert text.startswith("Nife: zeus, spawn a Hunter next to me")
    assert "- Rifleman by Nife (MX, 120 m)" in text
    assert "arma_say" in text and "Don't call arma_listen" in text
    assert "first say so in game" in text  # a big job gets a word first, so the player knows it's being done
    assert meta == {"from": "Nife", "to": "Zeus", "seq": "42"}
    assert display == "💬 Nife → Zeus: zeus, spawn a Hunter next to me"


def test_the_watcher_waits_for_a_game_then_delivers_each_message_once():
    calls, delivered, logged = [], [], []
    answers = iter([OSError("bridge unreachable"), OSError("bridge unreachable"),
                    {"found": False, "next": 5},
                    {"found": True, "next": 9, "message": {"name": "Nife", "text": "zeus, hi"}, "kills": []}])

    def listen(name, since, timeout):
        calls.append(since)
        answer = next(answers, None)
        if answer is None:
            time.sleep(0.05)
            return {"found": False, "next": since}
        if isinstance(answer, Exception):
            raise answer
        return answer

    wake = chatwake.ChatWake(listen, lambda: "Zeus", lambda *args: delivered.append(args), logged.append)
    wake.stop.wait = lambda seconds: time.sleep(0.01)  # no 5 s retries in a test
    wake.start()
    deadline = time.time() + 3
    while not delivered and time.time() < deadline:
        time.sleep(0.01)
    wake.stop.set()
    assert [args[0].split("\n")[0] for args in delivered] == ["Nife: zeus, hi"]
    assert len(logged) == 1  # the same problem twice is said once
    assert calls[:4] == [None, None, None, 5]  # from where it was, so nothing said meanwhile is missed


def test_the_watcher_survives_a_delivery_that_fails():
    answers = iter([{"found": True, "next": 1, "message": {"name": "A", "text": "zeus, a"}},
                    {"found": True, "next": 2, "message": {"name": "B", "text": "zeus, b"}}])
    delivered, logged = [], []

    def listen(name, since, timeout):
        answer = next(answers, None)
        if answer is None:
            time.sleep(0.05)
            return {"found": False, "next": since}
        return answer

    def deliver(text, meta, display):
        if meta["from"] == "A":
            raise OSError("client gone")
        delivered.append(meta["from"])

    wake = chatwake.ChatWake(listen, lambda: "Zeus", deliver, logged.append).start()
    deadline = time.time() + 3
    while not delivered and time.time() < deadline:
        time.sleep(0.01)
    wake.stop.set()
    assert delivered == ["B"] and "couldn't be delivered" in logged[0]


# -- the arma server as a Claude Code channel -------------------------------------------------------------------------

def game_on(home, monkeypatch=None):
    """A game run recorded in ``home``, its server this test process: alive for as long as the test runs."""
    from arma_harness.harness import Harness, Proc, RunState

    before = os.environ.get("BRMH_HOME")
    os.environ["BRMH_HOME"] = str(home)  # Harness finds its home here
    try:
        Harness()._save(RunState(
            run_id="r1", mode="launched", mission="demo", folder="", token="t", bridge_pid=os.getpid(), adapters=[],
            overrides={}, procs=[Proc(os.getpid(), "server", "server", "", "")], started=0.0))
    finally:
        if before is None:
            os.environ.pop("BRMH_HOME", None)
        else:
            os.environ["BRMH_HOME"] = before


def run_server(*requests, home):
    """The real arma MCP server over stdio, as a client starts it. Its input stays open until every request is
    answered: closing it at once shut the server down with the last answer still in flight, now and then."""
    proc = subprocess.Popen([sys.executable, "-m", "arma_harness.mcp_server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            env={**os.environ, "BRMH_HOME": str(home)})
    rows: dict = {}
    reader = threading.Thread(target=lambda: rows.update(
        (row["id"], row) for row in map(json.loads, proc.stdout) if "id" in row), daemon=True)
    reader.start()
    for request in requests:
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", **request}) + "\n")
    proc.stdin.flush()
    wanted = {request["id"] for request in requests if "id" in request}
    deadline = time.time() + 60
    while not wanted <= set(rows) and time.time() < deadline:
        time.sleep(0.05)
    proc.stdin.close()
    proc.wait(timeout=30)
    return rows


def test_the_server_is_a_channel_on_a_handshake_revision(tmp_path):
    """Claude Code asks for 2026-07-28, which has no handshake, and doesn't take a server that settles on it as a
    channel. A library upgrade that changed either answer would stop chat waking Claude Code, silently."""
    rows = run_server(
        {"id": 1, "method": "server/discover", "params": {}},
        {"id": 2, "method": "initialize", "params": {"protocolVersion": "2026-07-28", "capabilities": {},
                                                     "clientInfo": {"name": "claude-code", "version": "2"}}},
        home=tmp_path)
    assert rows[1]["error"]["code"] == -32601  # so the client falls back to initialize
    result = rows[2]["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert result["capabilities"]["experimental"] == {"claude/channel": {}}


@pytest.mark.parametrize(("client", "ok"), [("claude-code", True), ("codex-mcp-client", False)])
def test_chat_wake_answers_by_client(tmp_path, monkeypatch, client, ok):
    import anyio
    from mcp import Client
    from mcp.types import Implementation

    from arma_harness import mcp_server

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_harness", None)
    game_on(tmp_path)

    async def go():
        async with Client(mcp_server.server, client_info=Implementation(name=client, version="1"),
                          mode="legacy") as session:
            reply = json.loads((await session.call_tool("arma_chat_wake", {"test": False})).content[0].text)
            await session.call_tool("arma_chat_wake", {"on": False})
            return reply

    reply = anyio.run(go)
    assert reply["ok"] is ok
    if ok:
        assert reply["via"] == "claude code channel" and "--dangerously-load-development-channels" in reply["note"]
    else:
        assert "arma_listen" in reply["error"]


def test_a_wake_reaches_claude_code_as_a_channel_notification(tmp_path):
    """The real server over stdio, as Claude Code sees it: the test wake comes out as a channel notification."""
    game_on(tmp_path)
    proc = subprocess.Popen([sys.executable, "-m", "arma_harness.mcp_server"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                            env={**os.environ, "BRMH_HOME": str(tmp_path)})
    lines: list[dict] = []
    reader = threading.Thread(target=lambda: lines.extend(json.loads(line) for line in proc.stdout), daemon=True)
    reader.start()
    for message in ({"id": 1, "method": "initialize", "params": {
                        "protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "claude-code", "version": "2"}}},
                    {"method": "notifications/initialized"},
                    {"id": 2, "method": "tools/call", "params": {"name": "arma_chat_wake", "arguments": {}}}):
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
        proc.stdin.flush()
    try:
        deadline = time.time() + 20
        while time.time() < deadline and not any(row.get("method") == "notifications/claude/channel" for row in lines):
            time.sleep(0.1)
    finally:
        proc.stdin.close()
        proc.wait(timeout=20)
    wakes = [row for row in lines if row.get("method") == "notifications/claude/channel"]
    assert wakes, lines
    assert wakes[0]["params"]["content"].startswith("Chat wake test")
    assert wakes[0]["params"]["meta"]["test"] == "true"


def test_in_opencode_wakes_go_to_the_calling_session(tmp_path, monkeypatch):
    import anyio
    from mcp import Client
    from mcp.types import Implementation

    from arma_harness import mcp_server
    from arma_harness.commander import opencode

    posted = []

    class Server:
        def __init__(self, cli):
            pass

        def call(self, method, path, body=None):
            if path == "/api/session/active":
                return {"data": {"ses_me": {"type": "running"}}}
            if method == "GET":
                return {"data": {"location": {"directory": str(tmp_path)}}}
            posted.append((path, body))
            return {"data": {}}

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    game_on(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mcp_server, "_harness", None)
    monkeypatch.setattr(opencode, "Service", Server)

    async def go():
        async with Client(mcp_server.server, client_info=Implementation(name="opencode", version="2.2.7"),
                          mode="legacy") as session:
            reply = json.loads((await session.call_tool("arma_chat_wake", {"test": False})).content[0].text)
            await anyio.to_thread.run_sync(mcp_server._wake.deliver, "Nife: zeus, hi", {"from": "Nife"},
                                           "💬 Nife → Zeus: zeus, hi")
            await anyio.sleep(0.3)
            await session.call_tool("arma_chat_wake", {"on": False})
            return reply

    reply = anyio.run(go)
    assert reply["ok"] and reply["via"] == "opencode session ses_me"
    path, body = posted[0]
    assert path == "/api/session/ses_me/prompt"
    assert body["text"].startswith('<channel source="arma" from="Nife">\nNife: zeus, hi')
    assert body["metadata"]["displayText"] == "💬 Nife → Zeus: zeus, hi"
    assert body["delivery"] == "queue"


def test_claude_codes_opening_ends_in_the_handshake_not_a_dead_end(tmp_path):
    """Claude Code opens with a stateless server/discover. The library let that make the whole connection stateless,
    which then refused the initialize Claude Code fell back to with -32022, the one error it doesn't fall back from:
    the arma tools didn't connect at all. Now the stateless request is refused in a way clients do fall back from."""
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {},
            "io.modelcontextprotocol/clientInfo": {"name": "claude-code", "version": "2"}}
    rows = run_server(
        {"id": 1, "method": "server/discover", "params": {"_meta": meta}},
        {"id": 2, "method": "initialize", "params": {"protocolVersion": "2026-07-28", "capabilities": {},
                                                     "clientInfo": {"name": "claude-code", "version": "2"}}},
        {"method": "notifications/initialized"},
        {"id": 3, "method": "tools/list", "params": {}},
        home=tmp_path)
    assert rows[1]["error"]["code"] not in (-32022,)  # anything else, and the client falls back to initialize
    assert rows[2]["result"]["protocolVersion"] == "2025-11-25"
    assert rows[2]["result"]["capabilities"]["experimental"] == {"claude/channel": {}}
    assert "arma_chat_wake" in {tool["name"] for tool in rows[3]["result"]["tools"]}


def test_a_wake_needs_a_game(tmp_path, monkeypatch):
    import anyio
    from mcp import Client
    from mcp.types import Implementation

    from arma_harness import mcp_server

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_harness", None)

    async def go():
        async with Client(mcp_server.server, client_info=Implementation(name="claude-code", version="2"),
                          mode="legacy") as session:
            return json.loads((await session.call_tool("arma_chat_wake", {"test": False})).content[0].text)

    reply = anyio.run(go)
    assert reply["ok"] is False and "attach" in reply["error"]


def test_a_wake_ends_with_its_game():
    """It used to wait for the next game: a server left in OpenCode's background service took up the user's next
    game and would have posted their chat into a session nobody could see."""
    runs = iter(["r1", "r1", None])
    ended, delivered = [], []

    def listen(name, since, timeout):
        time.sleep(0.01)
        return {"found": False, "next": since}

    wake = chatwake.ChatWake(listen, lambda: "Zeus", lambda *a: delivered.append(a), lambda text: None,
                             run=lambda: next(runs, None), ended=ended.append).start()
    wake.thread.join(3)
    assert not wake.thread.is_alive() and wake.stop.is_set()
    assert ended == ["its game has closed or been detached"]


def test_another_game_ends_a_wake_too():
    runs = iter(["r1", "r2"])
    ended = []

    def listen(name, since, timeout):
        raise OSError("bridge unreachable")

    wake = chatwake.ChatWake(listen, lambda: "Zeus", lambda *a: None, lambda text: None,
                             run=lambda: next(runs, "r2"), ended=ended.append).start()
    wake.thread.join(3)
    assert ended == ["another game has been attached"]


def test_a_name_held_by_a_session_that_stopped_listening_comes_free(tmp_path, monkeypatch):
    """A server idling in OpenCode's background service kept "Luna" from every new session."""
    from arma_harness import harness as harness_mod
    from arma_harness.harness import Harness, HarnessError

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    other = os.getppid()  # alive, and not us
    stale = {"name": "Luna", "pid": other, "claimed": time.time() - 3600, "since": 1,
             "started": time.time() - 3600, "deadline": time.time() - 3540, "finished": None}
    h._listener("Luna", stale)
    assert h.claim_name("Luna")["name"] == "Luna"

    h._listener("Luna", {**stale, "deadline": time.time() + 30})  # listening right now
    with pytest.raises(HarnessError, match="is listening"):
        h.claim_name("Luna")
    h._listener("Luna", {**stale, "wake": "opencode session ses_x"})  # a wake on
    with pytest.raises(HarnessError, match="is listening"):
        h.claim_name("Luna")
    monkeypatch.setattr(harness_mod, "NAME_IDLE_S", 0)
    h._listener("Luna", {**stale, "finished": time.time() - 1})
    assert h.claim_name("Luna")["name"] == "Luna"


def test_the_wake_note_survives_the_listeners_own_updates(tmp_path, monkeypatch):
    """The wake's thread rewrote the record after each listen, and the note that the wake was on went with it."""
    from arma_harness.harness import Harness

    monkeypatch.setenv("BRMH_HOME", str(tmp_path))
    h = Harness()
    h.claim_name("Zeus")
    h.set_wake("Zeus", "claude code channel")
    h.claim_name("Zeus")  # as every listen does
    assert h._listener("Zeus")["wake"] == "claude code channel"


def test_a_server_running_older_code_says_so(monkeypatch):
    """OpenCode's service kept a server running after the harness changed: the agent's channel went unheard."""
    from arma_harness import mcp_server

    assert mcp_server.code_changed() is None
    monkeypatch.setattr(mcp_server, "_LOADED", mcp_server._code_stamp() - 60)
    warning = mcp_server.code_changed()
    assert "running the old version" in warning and "opencode service restart" in warning
