"""Live check of commander mode: a scripted stand-in for the LLM plays real scenarios on a real game.

    host\\.venv\\Scripts\\python.exe host\\tests\\live_commander.py

It talks to the real MCP server over stdio, exactly as a client would, and boots a headless server if none is
running. It proves the plumbing. Whether a real LLM commands sensibly is a separate question.
"""
from __future__ import annotations

import base64
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


def save_map(client: Client, label: str, **args) -> None:
    """The commander's map, written where a person can look at it."""
    result = client.request("tools/call", {"name": "commander_map", "arguments": args})
    assert not result.get("isError"), result
    file = Harness().home.captures / f"commander_map_{label}.png"
    file.write_bytes(base64.b64decode(result["content"][0]["data"]))
    print(f"    map {label}: {file}", flush=True)


def timer_fired(wake: dict, note: str) -> bool:
    """Whether this wake is that timer coming due: a pending one is also listed in every briefing."""
    due = wake["content"].split("TIMERS DUE", 1)
    return len(due) == 2 and note in due[1].split(chr(10) * 2, 1)[0]


def play_orders(client: Client) -> list[str]:
    """Every building and CBA order on a real game, and above all: can a later order get a squad back out of it?"""
    brief = begin(client)
    ids = [building["id"] for building in brief["buildings"]]
    print("    buildings:", brief["buildings"], flush=True)
    assert len(ids) >= 3, brief["buildings"]
    save_map(client, "orders")
    first, second = ids[0], ids[1]
    # A 4-man squad takes minutes over a big building, and this checks the reporting, not their stamina.
    smallest = [b["id"] for b in sorted(brief["buildings"], key=lambda b: b["positions"])[:2]]
    orders = {"Occupy": {"type": "OCCUPY", "at": first}, "Cordon": {"type": "CORDON", "at": second, "radius": 25},
              "Defend": {"type": "DEFEND", "at": "041 041", "radius": 120},
              "Attack": {"type": "ATTACK", "at": "041 041", "radius": 80},
              "Sweep": {"type": "SWEEP", "at": "041 041", "radius": 120},
              "Patrol": {"type": "PATROL_AREA", "at": "043 041", "radius": 80},
              "Clear": {"type": "CLEAR", "at": smallest}}
    for callsign, leg in orders.items():
        client.tool("commander_order", to=callsign, legs=[leg])
    client.tool("commander_schedule", after="3:30", do={"wake": "Check that everyone got there"})
    finish_turn(client, "All orders out")
    seen = []
    while True:
        wake = next_wake(client)
        seen.append(wake["content"])
        finish_turn(client, "Read the traffic")
        if timer_fired(wake, "Check that everyone got there"):
            break
    for callsign in orders:
        print("    task:", client.tool("commander_ask", to=callsign, topics=["position", "task"]), flush=True)
    save_map(client, "orders_after")
    # Everybody leaves. DEFEND is the one that needs special handling to let go.
    start = {r["from"]: r["text"] for r in client.tool("commander_ask", to="all", topics=["position"])["replies"]}
    for callsign in orders:
        client.tool("commander_order", to=callsign, legs=[{"type": "MOVE", "at": "041 034"}])
    client.tool("commander_schedule", after="2:30", do={"wake": "Did everyone get out?"})
    finish_turn(client, "All pulled out")
    while True:
        wake = next_wake(client)
        seen.append(wake["content"])
        finish_turn(client, "Read the traffic")
        if timer_fired(wake, "Did everyone get out?"):
            break
    after = {r["from"]: r["text"] for r in client.tool("commander_ask", to="all", topics=["position"])["replies"]}
    print("    pulled out, from:", start, "\n    to:", after, flush=True)
    moved = [callsign for callsign in orders if start[callsign][:12] != after[callsign][:12]]
    assert set(moved) == set(orders), f"still in place after a new order: {set(orders) - set(moved)}"
    text = "\n".join(seen)
    wanted = (f"Copy, occupying {first}", f"In position, occupying {first}",
              f"Copy, setting a cordon around {second}", f"In position, cordon around {second}",
              "Copy, defending grid 041 041", "Copy, attacking grid 041 041", "Copy, sweeping around grid 041 041",
              f"{smallest[0]} checked, nothing seen", f"{smallest[1]} checked, nothing seen",
              f"Finished checking {smallest[0]}, {smallest[1]}")
    for expected in wanted:
        assert expected in text, expected
    return seen


def snap(harness: Harness, label: str) -> None:
    try:
        print(f"    snapshot {label}: {harness.snapshot(max_width=1100)['path']}", flush=True)
    except Exception as exc:  # a missing picture shouldn't fail a battle
        print(f"    snapshot {label} failed: {exc}", flush=True)


def heard(client: Client, phrase: str, timeout: float = 180) -> str:
    """Reads wakes until a phrase turns up, ending each turn as it goes."""
    deadline, text = time.time() + timeout, ""
    while time.time() < deadline:
        wake = next_wake(client, max(1, deadline - time.time()))
        text += wake["content"]
        finish_turn(client, "Read the traffic")
        if phrase in text:
            return text
    raise AssertionError(f"never heard {phrase!r}: {text[-900:]}")


def in_game(harness: Harness, code: str, args: list | None = None):
    res = harness.exec(code, "server", timeout=15, args=args, strip=False)
    result = res["results"][0] if res.get("results") else res
    assert res.get("ok") and not result.get("errors"), result
    return result.get("r")


def play_vehicles(client: Client) -> list[str]:
    """Vehicles, seats and ruins, on the real game. Each step's words are what the commander really gets."""
    harness = Harness()
    brief = begin(client)
    known = {vehicle["id"]: vehicle for vehicle in brief["vehicles"]}
    assert set(known) == {"V1", "V3"} and known["V1"]["type"] == "Mk6 Mortar", brief["vehicles"]
    client.tool("commander_end_turn", note="Waiting", messages_only=True)

    # Alpha can see the unlisted mortar. The id it gets is the commander's own, not the scenario's.
    text = heard(client, "Listed as V")
    assert "Mk6 Mortar, nobody on it, grid 041 035. Listed as V" in text, text[-500:]
    assert "is destroyed" not in text, "a standing building was reported destroyed"

    # Mount by seat: a subordinate gets on, not the leader, and targeting goes off.
    client.tool("commander_order", to="Hammer", legs=[{"type": "MOUNT", "vehicle": "V1", "seat": "gunner"}])
    text = heard(client, "on V1 as gunner")
    assert "Copy, mounting V1 as gunner." in text and "didn't fit" not in text
    seat = in_game(harness, """
    private _gun = brmh_cmd_vehicles get "V1";
    private _group = brmh_cmd_stations get "Hammer";
    [gunner _gun isNotEqualTo objNull, gunner _gun isEqualTo leader _group, (gunner _gun) checkAIFeature "TARGET"]
    """)
    assert seat == [True, False, False], seat
    answer = client.tool("commander_ask", to="Hammer", topics=["vehicles"])["replies"][0]["text"]
    assert "On V1:" in answer and "as gunner" in answer and "2 on foot" in answer, answer

    # A taken seat is said aloud, not left waiting in silence. There's no such seat on a mortar as a driver's.
    client.tool("commander_order", to="Alpha", legs=[{"type": "MOUNT", "vehicle": "V1", "seat": "gunner"}])
    assert "Unable, V1's gunner seat is taken." in heard(client, "seat is taken", 30)
    client.tool("commander_order", to="Alpha", legs=[{"type": "MOUNT", "vehicle": "V1", "seat": "driver"}])
    assert "Unable, V1 has no driver seat." in heard(client, "no driver seat", 30)

    # The squad moves off, and its man stays on the gun.
    client.tool("commander_order", to="Hammer", legs=[{"type": "MOVE", "at": "038 039"}])
    text = heard(client, "stays on V1", 30)
    time.sleep(25)
    apart = in_game(harness, """
    private _gun = brmh_cmd_vehicles get "V1";
    private _group = brmh_cmd_stations get "Hammer";
    [round (leader _group distance2D _gun), vehicle (gunner _gun) isEqualTo _gun]
    """)
    assert apart[0] > 30 and apart[1], apart

    # A gunner down is reported by his squad, and the seat can be taken again.
    in_game(harness, 'gunner (brmh_cmd_vehicles get "V1") setDamage 1; true')
    heard(client, "Gunner down on V1", 40)

    # A whole squad into a truck, driven by a subordinate, then out.
    client.tool("commander_order", to="Alpha", legs=[{"type": "MOUNT", "vehicle": "V3"}])
    text = heard(client, "on V3", 120)
    client.tool("commander_order", to="Alpha", legs=[{"type": "MOVE", "at": "039 040"}])
    heard(client, "Arrived, grid", 120)
    client.tool("commander_order", to="Alpha", legs=[{"type": "DISMOUNT", "vehicle": "V3"}])
    heard(client, "Off V3.", 60)
    assert client.tool("commander_ask", to="Alpha", topics=["vehicles"])["replies"][0]["text"] == "All on foot."

    # A wreck, seen and then refused. Then a ruin: it's seen, and clearing it says so and moves on.
    # No explosion: Alpha is standing right beside it, and would be wiped out with nobody left to report.
    in_game(harness, '(brmh_cmd_vehicles get "V3") setDamage [1, false]; true')
    heard(client, "V3 is wrecked", 60)
    print("    Alpha alive:", in_game(harness, '{alive _x} count units (brmh_cmd_stations get "Alpha")'), flush=True)
    client.tool("commander_order", to="Alpha", legs=[{"type": "MOUNT", "vehicle": "V3"}])
    heard(client, "V3 is wrecked. Not mounting.", 40)
    ids = sorted(brief["buildings"], key=lambda b: b["positions"])
    gone, kept = ids[0]["id"], ids[1]["id"]
    in_game(harness, "(brmh_cmd_buildings get (_this # 0)) params ['_x', '_y']; "
            "(nearestObjects [[_x, _y, 0], ['House'], 6]) apply { _x setDamage 1 }; true", [gone])
    client.tool("commander_order", to="Alpha", legs=[{"type": "CLEAR", "at": [gone, kept]}])
    text = heard(client, f"{kept} checked", 240)
    assert f"{gone} is a ruin" in text or f"{gone} is destroyed" in text, text[-800:]
    assert f"{gone} checked" not in text, "a ruin was reported as checked"
    return [text]


def play_fire(client: Client) -> list[str]:
    """Fire missions on the real game, by the commander's own tools. The rounds land on empty ground."""
    harness = Harness()
    begin(client)
    client.tool("commander_end_turn", note="Waiting", messages_only=True)
    time.sleep(3)
    assert in_game(harness, """
    private _gun = brmh_cmd_vehicles get "V1";
    [(gunner _gun) checkAIFeature "TARGET", gunner _gun isEqualTo leader group gunner _gun, count crew _gun]
    """) == [False, False, 1]

    log = []

    def hear(phrase, timeout):
        log.append(heard(client, phrase, timeout))
        return log[-1]

    def fire(to="Hammer", **leg):
        return client.tool("commander_order", to=to, legs=[{"type": "FIRE_MISSION", **leg}])

    answer = client.tool("commander_ask", to="Hammer", topics=["ammo"])["replies"][0]["text"]
    assert "V1: 16 HE, 4 SMOKE." in answer, answer

    # A mission: acknowledgement, shot with a time of flight, and rounds complete with what's left.
    fire(at="028 020", rounds=2)
    text = hear("Rounds complete", 60)
    assert "Copy, fire mission, 2 HE at grid 028 020." in text, text[-700:]
    assert "Shot, 2 rounds, splash in about" in text, text[-700:]
    assert "14 HE left." in text

    # 8 figures, and the impact goes where it should. A token is refused by the tool.
    fire(at="0281 0203", rounds=1)
    hear("13 HE left", 60)
    result = client.request("tools/call", {"name": "commander_order", "arguments": {
        "to": "Hammer", "legs": [{"type": "FIRE_MISSION", "at": "V1"}]}})
    assert result.get("isError") and "grid reference" in result["content"][0]["text"], result

    # Too far, too near, and a station with no gun: each said aloud, with no rounds wasted.
    fire(at="080 020")
    hear("Unable, out of range.", 30)
    fire(at="020 020")
    hear("Unable, out of range.", 30)
    fire(to="Alpha", at="070 020")
    hear("Unable, no gun crewed.", 30)

    # Across a magazine: more than one holds, and it says when it runs out. Smoke is its own count.
    fire(at="028 020", rounds=12)
    text = hear("Rounds complete", 90)
    assert "1 HE left." in text, text[-500:]
    fire(at="028 020", rounds=3)
    text = hear("Out of HE", 60)
    assert "Out of HE, 1 of 3 fired." in text, text[-500:]
    fire(at="028 020", ammo="SMOKE", rounds=1)
    hear("3 SMOKE left", 60)
    fire(at="028 020", rounds=1)
    hear("Unable, out of HE.", 30)

    # Weapons tight: it holds and says so, and goes when released. BLUE can't stop what's already running.
    client.tool("commander_order", to="Hammer", legs=[{"type": "POSTURE"}], combat_mode="GREEN")
    fire(at="028 020", ammo="SMOKE", rounds=1)
    hear("Holding, weapons tight.", 40)
    client.tool("commander_order", to="Hammer", legs=[{"type": "POSTURE"}], combat_mode="YELLOW")
    hear("2 SMOKE left", 60)

    # Check fire stops a mission with rounds to go, and it says what's still coming.
    in_game(harness, '[(brmh_cmd_vehicles get "V1"), [["HE", 16], ["SMOKE", 2]]] call brmh_cmd_fnc_setAmmo; true')
    fire(at="028 020", rounds=8)
    hear("Shot, 8 rounds", 30)
    time.sleep(1)
    client.tool("commander_order", to="Hammer", legs=[{"type": "CHECK_FIRE"}])
    assert "still in the air" in hear("rounds still in the air", 30)
    left = client.tool("commander_ask", to="Hammer", topics=["ammo"])["replies"][0]["text"]
    time.sleep(12)
    assert left == client.tool("commander_ask", to="Hammer", topics=["ammo"])["replies"][0]["text"], "it kept firing"
    fired = 16 - int(left.split("V1: ")[1].split(" HE")[0])
    assert 1 <= fired < 8, left

    # The fourth silent failure: a Scorcher that says it can reach, and doesn't fire.
    fire(to="Anvil", at="040 050", rounds=2)
    text = hear("Unable, can't lay on that target.", 60)

    # A dead gunner.
    in_game(harness, 'gunner (brmh_cmd_vehicles get "V1") setDamage 1; true')
    hear("Gunner down on V1", 30)
    fire(at="028 020", rounds=1)
    hear("Unable, no gun crewed.", 30)
    fire(at="028 020", rounds=1, guns=["V1"])
    hear("Unable, no gunner on V1.", 30)
    # The engine's hidden target at each aim point is nobody's enemy.
    assert not [text for text in log if "Contact" in text], log
    return log


def play_village(client: Client) -> list[str]:
    """Plumbing for the combat scenario: timed attack, repeating check-in, markers, contact reports, an ending."""
    harness = Harness()
    brief = begin(client)
    assert len(brief["buildings"]) >= 5, brief["buildings"]
    save_map(client, "village_start")
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
    seen, marked, clearing, deadline = [], 0, set(), time.time() + 25 * 60
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
            # A squad in a fight should stall, then answer by message, with no grid unless asked for its position.
            for callsign in ("Alpha", "Recon"):
                print(f"    asked {callsign} mid-fight:", client.tool("commander_ask", to=callsign), flush=True)
        if len(seen) == 6:
            snap(harness, "mid battle")
        # Send everyone in once they've finished sweeping or have stalled: SEARCH alone leaves garrisons untouched, and
        # it can go on for the whole battle while there's still an enemy it knows of.
        for callsign in ("Alpha", "Bravo", "Charlie"):
            if callsign not in clearing and (f"{callsign}: Finished searching" in wake["content"]
                                             or f"{callsign}: Not making progress" in wake["content"]):
                clearing.add(callsign)
                client.tool("commander_order", to=callsign, legs=[{"type": "CLEAR", "at": "O1", "radius": 130}])
                print(f"    {callsign} ordered to clear", flush=True)
        finish_turn(client, "Read the traffic")
    snap(harness, "end")
    save_map(client, "village_end")
    text = "\n".join(seen)
    assert "Contact," in text, "no contact report in the whole battle"
    assert "E1  enemy First contact  grid 041 040" in text or marked == 0
    assert "H1  hypothesis Enemy in village  grid 041 041  low" in text
    assert "checked, " in text, "no squad reported checking a building"
    gridded = [line for line in text.splitlines() if "Contact" in line and "grid" in line.lower()]
    assert not gridded, f"contact reports stating a grid: {gridded[:3]}"
    return seen


def run(name: str, scenario: str, mode: str | None, play, watch: bool = False) -> None:
    print(f"\n========== {name} ==========", flush=True)
    harness = Harness()
    # LIVE_NO_WATCH=1: nobody's watching, so don't open a game window.
    started = operator.start(scenario, mode, harness, watch=watch and not os.environ.get("LIVE_NO_WATCH"))
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
               ("every order type", "orders_check", "hold", play_orders),
               ("vehicles and crews", "vehicles_check", "hold", play_vehicles),
               ("fire missions", "fire_check", "hold", play_fire),
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
