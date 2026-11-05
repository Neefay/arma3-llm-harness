"""Live check of commander mode: a scripted stand-in for the LLM plays real scenarios on a real game.

    host\\.venv\\Scripts\\python.exe host\\tests\\live_commander.py

It talks to the real MCP server over stdio, exactly as a client would, and boots a headless server if none is
running. It proves the plumbing. Whether a real LLM commands sensibly is a separate question.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time

from arma_harness.commander import operator
from arma_harness.harness import Harness

THINKING_S = 6  # a stand-in for the LLM's response time, so messages land during its turns


class Client:
    def __init__(self):
        self.proc = subprocess.Popen([sys.executable, "-m", "arma_harness.commander.server"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, env=os.environ.copy())
        self.next_id = 0
        self.answers: dict[int, dict] = {}
        self.cond = threading.Condition()
        self.wakes: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        init = self.request("initialize", {"protocolVersion": "2025-06-18"})
        assert init["capabilities"]["experimental"]["claude/channel"] == {}, init

    def _read(self) -> None:
        for raw in self.proc.stdout:
            message = json.loads(raw)
            if "id" in message:
                with self.cond:
                    self.answers[message["id"]] = message
                    self.cond.notify_all()
            elif message.get("method") == "notifications/claude/channel":
                self.wakes.put(message["params"])

    def request(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        rid = self.next_id
        self.proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
                               + "\n").encode())
        self.proc.stdin.flush()
        with self.cond:
            while rid not in self.answers:
                if not self.cond.wait(60):
                    raise TimeoutError(method)
            return self.answers.pop(rid).get("result", {})

    def tool(self, name: str, **args):
        result = self.request("tools/call", {"name": name, "arguments": args})
        text = result["content"][0]["text"]
        assert not result.get("isError"), f"{name} {args}: {text}"
        try:
            return json.loads(text)
        except ValueError:
            return text

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait(15)


def begin(client: Client) -> dict:
    deadline = time.time() + 60
    while time.time() < deadline:
        brief = client.tool("commander_mission")
        if brief.get("mission"):
            return brief
        time.sleep(1)
    raise TimeoutError("the net never came up")


def next_wake(client: Client, timeout: float = 240) -> dict:
    wake = client.wakes.get(timeout=timeout)
    print(f"\n--- WAKE turn {wake['meta']['turn']}: {wake['meta']['woke_on']}\n{wake['content']}", flush=True)
    return wake


def finish_turn(client: Client, note: str) -> None:
    result = client.tool("commander_end_turn", note=note)
    if not result["ended"]:
        client.tool("commander_end_turn", note=note, messages_only=True)


def play_a_to_b(client: Client, mode: str) -> list[str]:
    begin(client)
    assert client.tool("commander_order", to="Alpha", legs=[{"type": "MOVE", "at": "B"}])["sent"]
    client.tool("commander_schedule", after="1:00", do={"wake": "Has Alpha arrived?"})
    client.tool("commander_notes", text="Plan: send Alpha to B, check at 1:00.")
    time.sleep(THINKING_S)
    mid_turn = not client.wakes.empty()
    assert mid_turn == (mode == "deliver"), f"{mode}: wake during a turn = {mid_turn}"
    finish_turn(client, "Sent Alpha")
    seen = []
    while True:
        wake = next_wake(client)
        seen.append(wake["content"])
        if "MISSION END" in wake["content"]:
            finish_turn(client, "Over")
            break
        if "TIMERS DUE" in wake["content"] and not any("Arrived" in text for text in seen):
            print("    asked:", client.tool("commander_ask", to="Alpha"), flush=True)
        finish_turn(client, "Read the traffic")
    text = "\n".join(seen)
    for expected in ("Copy, moving to grid 034 030", "Arrived, grid 034 030", "MISSION END. Objective achieved"):
        assert expected in text, expected
    return seen


def play_lost(client: Client) -> list[str]:
    begin(client)
    client.tool("commander_order", to="Alpha", legs=[{"type": "MOVE", "at": "B"}])
    client.tool("commander_schedule", after="1:00", do={"wake": "Has Alpha arrived?"})
    finish_turn(client, "Sent Alpha")
    seen, no_answer = [], None
    while True:
        wake = next_wake(client)
        seen.append(wake["content"])
        if "MISSION END" in wake["content"]:
            finish_turn(client, "Over")
            break
        if "TIMERS DUE" in wake["content"]:
            no_answer = client.tool("commander_ask", to="Alpha")
            print("    asked:", no_answer, flush=True)
        finish_turn(client, "Waiting")
    assert no_answer == {"replies": [{"from": "Alpha", "text": "No answer."}]}, no_answer
    text = "\n".join(seen)
    assert "Arrived" not in text and "Has Alpha arrived?" in text and "Time limit reached" in text
    return seen


def play_halt_and_resume(client: Client) -> list[str]:
    """The spike left this open: does a new order release a group stopped with doStop? Also checks POSTURE."""
    begin(client)
    client.tool("commander_order", to="Alpha", legs=[{"type": "MOVE", "at": "B"}], speed="FULL", behaviour="SAFE")
    finish_turn(client, "Sent Alpha")
    next_wake(client)
    time.sleep(10)
    moving = client.tool("commander_ask", to="Alpha", topics=["position", "task", "eta"])
    print("    moving:", moving, flush=True)
    client.tool("commander_order", to="Alpha", legs=[{"type": "HALT"}])
    finish_turn(client, "Halting")
    assert "Halted at grid" in next_wake(client)["content"]
    time.sleep(6)
    first = client.tool("commander_ask", to="Alpha", topics=["position"])
    time.sleep(10)
    second = client.tool("commander_ask", to="Alpha", topics=["position"])
    print("    halted:", first, second, flush=True)
    assert "stationary" in second["replies"][0]["text"], second
    client.tool("commander_order", to="Alpha", legs=[{"type": "POSTURE"}], combat_mode="BLUE")
    finish_turn(client, "Posture")
    assert "Copy." in next_wake(client)["content"]
    client.tool("commander_order", to="Alpha", legs=[{"type": "HOLD", "at": "B"}])
    client.tool("commander_schedule", after="2:00", do={"wake": "Did Alpha get moving again?"})
    finish_turn(client, "Resuming")
    seen = []
    while True:
        wake = next_wake(client)
        seen.append(wake["content"])
        if "MISSION END" in wake["content"]:
            finish_turn(client, "Over")
            break
        finish_turn(client, "Waiting")
    assert "MISSION END. Objective achieved" in "\n".join(seen), "a new order didn't release the halted group"
    return seen


def snap(harness: Harness, label: str) -> None:
    try:
        print(f"    snapshot {label}: {harness.snapshot(max_width=1100)['path']}", flush=True)
    except Exception as exc:  # a missing picture shouldn't fail a battle
        print(f"    snapshot {label} failed: {exc}", flush=True)


def play_village(client: Client) -> list[str]:
    """Plumbing for the combat scenario: timed attack, repeating check-in, markers, contact reports, an ending."""
    harness = Harness()
    begin(client)
    snap(harness, "start")
    client.tool("commander_order", to="Recon", legs=[{"type": "MOVE", "at": "041 038"}], behaviour="STEALTH")
    client.tool("commander_mark", id="H1", kind="hypothesis", at="041 041", label="Enemy in village", confidence="low")
    for callsign in ("Alpha", "Bravo", "Charlie"):
        made = client.tool("commander_schedule", after="0:30", do={"order": {
            "to": callsign, "legs": [{"type": "SEARCH", "at": "O1", "radius": 120}], "speed": "FULL"}})
        print("    timed:", made, flush=True)
    client.tool("commander_schedule", every="1:00", do={"ask": {"to": "Recon", "topics": ["position", "contacts"]}})
    client.tool("commander_schedule", every="2:00", do={"wake": "Regular check"})
    finish_turn(client, "Recon forward, attack at 0:30")
    seen, marked, clearing, deadline = [], 0, set(), time.time() + 19 * 60
    while time.time() < deadline:
        wake = next_wake(client, 240)
        seen.append(wake["content"])
        if "MISSION END" in wake["content"]:
            finish_turn(client, "Over")
            break
        if marked == 0 and "Contact," in wake["content"]:
            client.tool("commander_mark", id="E1", kind="enemy", at="041 040", label="First contact",
                        confidence="medium")
            marked = 1
            snap(harness, "first contact")
        if len(seen) == 6:
            snap(harness, "mid battle")
        # Send everyone in once they've finished sweeping: SEARCH alone leaves garrisons untouched.
        for callsign in ("Alpha", "Bravo", "Charlie"):
            if callsign not in clearing and f"{callsign}: Finished searching" in wake["content"]:
                clearing.add(callsign)
                client.tool("commander_order", to=callsign, legs=[{"type": "CLEAR", "at": "O1", "radius": 130}])
                print(f"    {callsign} ordered to clear", flush=True)
        finish_turn(client, "Read the traffic")
    snap(harness, "end")
    text = "\n".join(seen)
    assert "Contact," in text, "no contact report in the whole battle"
    assert "E1  enemy First contact  grid 041 040" in text or marked == 0
    assert "H1  hypothesis Enemy in village  grid 041 041  low" in text
    assert "Copy, clearing buildings around grid 041 041" in text, "no squad was ordered to clear"
    return seen


def run(name: str, scenario: str, mode: str | None, play, watch: bool = False) -> None:
    print(f"\n========== {name} ==========", flush=True)
    harness = Harness()
    started = operator.start(scenario, mode, harness, watch=watch)
    print(json.dumps({k: v for k, v in started.items() if k != "launch"}), flush=True)
    client = Client()
    try:
        play(client)
    finally:
        client.close()
    print(f"\n--- AFTER ACTION: {name}\n{operator.aar(harness.home)}", flush=True)
    print(json.dumps(operator.status(harness.home), indent=1), flush=True)
    errors = [e for e in harness.events(since=0, kinds=["err"]).get("events", [])]
    assert not errors, errors[:3]
    print(f"PASS: {name}", flush=True)


def main() -> None:
    harness = Harness()
    battles = [("hold mode, A to B", "poc_a_to_b", "hold", lambda c: play_a_to_b(c, "hold")),
               ("deliver mode, A to B", "poc_a_to_b", "deliver", lambda c: play_a_to_b(c, "deliver")),
               ("failure variant: Alpha lost", "poc_a_to_b_lost", "hold", play_lost),
               ("halt, posture and resume", "poc_a_to_b", "hold", play_halt_and_resume),
               ("combat: take the village", "take_the_village", "hold", play_village, True)]
    wanted = sys.argv[1:]  # words to match in battle names; none means all of them
    try:
        for battle in battles:
            if not wanted or any(word in battle[0] for word in wanted):
                run(*battle)
        print("\nALL PASSED", flush=True)
    finally:
        print(harness.stop(), flush=True)


if __name__ == "__main__":
    main()
