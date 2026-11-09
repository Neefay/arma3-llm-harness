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
from arma_harness.commander import scenario as scenario_mod
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
    # Measured on arrival: the squad may start on the far side of the gun, and walk right past it on the way.
    text += heard(client, "Arrived", 180)
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

    # A man who can't get off is said to be stuck, where getting off used to wait on him for good.
    client.tool("commander_order", to="Hammer", legs=[{"type": "MOUNT", "vehicle": "V1", "seat": "gunner"}])
    text += heard(client, "on V1 as gunner", 120)
    in_game(harness, """
    private _gun = brmh_cmd_vehicles get "V1";
    [{
        params ["_args", "_handle"];
        _args params ["_man", "_gun", "_until"];
        if (time > _until) exitWith {
            [_handle] call CBA_fnc_removePerFrameHandler;
        };
        if (vehicle _man isEqualTo _man) then {
            _man moveInGunner _gun;
        };
    }, 0, [gunner _gun, _gun, time + 50]] call CBA_fnc_addPerFrameHandler;
    true
    """)
    client.tool("commander_order", to="Hammer", legs=[{"type": "DISMOUNT"}])
    text += heard(client, "Can't get", 60)
    assert "off the vehicle." in text, text[-500:]
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

    # The engine's hidden target at each aim point is nobody's enemy.
    assert not [text for text in log if "Contact" in text], log

    # What other stations make of it. Bravo is 200 m from everything so far, and has been hearing it.
    assert not [text for text in log if "Under indirect fire" in text], log
    assert [text for text in log if "Explosions to the west, roughly 200 metres" in text], log
    assert [text for text in log if "Splash seen, grid 028 020, about 200 m east of us." in text], log

    # An assigned observer, and a round close enough to Bravo to be its problem.
    result = client.request("tools/call", {"name": "commander_order", "arguments": {
        "to": "Hammer", "legs": [{"type": "FIRE_MISSION", "at": "028 020", "observer": "Bravo"}]}})
    assert result.get("isError") and "isn't trained" in result["content"][0]["text"], result
    time.sleep(35)  # let the dust of the checked mission settle
    fire(at="028 020", rounds=1, observer="Recon")
    text = hear("seen.", 90)
    assert "of your grid. 1 round seen." in text or "Splash on your grid" in text, text[-500:]
    fire(at="0298 0205", rounds=1)
    hear("Under indirect fire, explosions about", 90)

    # Smoke is seen land too, and isn't called incoming.
    time.sleep(15)
    fire(at="028 020", ammo="SMOKE", rounds=1, observer="Recon")
    assert "1 round seen." in hear("seen.", 90)

    # Against the enemy it can see. Recon keeps sight of a man, and calls the round against where it thinks he is.
    time.sleep(15)
    in_game(harness, """
    private _group = createGroup [east, true];
    private _man = _group createUnit ["O_Soldier_F", [2800, 2050, 0], [], 0, "CAN_COLLIDE"];
    _man disableAI "ALL";
    _man allowDamage false;
    [_man] spawn {
        params ["_man"];
        while {
            alive _man
        } do {
            (brmh_cmd_stations get "Recon") reveal [_man, 4];
            sleep 2;
        };
    };
    true
    """)
    hear("Contact", 40)
    fire(at="0282 0205", rounds=1, observer="Recon")
    text = hear("seen.", 90)
    assert "of the enemy at bearing" in text or "Splash on the enemy at bearing" in text, text[-500:]

    # A leg wound, which a squad says, and which the game's own measures don't.
    in_game(harness, 'leader (brmh_cmd_stations get "Bravo") setHitPointDamage ["hitLegs", 0.6]; true')
    assert "Slow going," in hear("hit in the legs", 90)  # Bravo can be in a fight by now, and slow to say so
    answer = client.tool("commander_ask", to="Bravo", topics=["strength"])["replies"][0]["text"]
    assert "hit in the legs." in answer, answer

    # The fourth silent failure: a Scorcher that says it can reach, and doesn't fire.
    fire(to="Anvil", at="040 050", rounds=2)
    text = hear("Unable, can't lay on that target.", 60)

    # Move up and fire, as one order: the gunner stays on the mortar while the rest move, then the fire step runs.
    client.tool("commander_order", to="Hammer", legs=[{"type": "MOVE", "at": "020 022"},
                                                      {"type": "FIRE_MISSION", "at": "028 020", "rounds": 1}])
    text = hear("then fire mission, 1 HE at grid 028 020.", 30)
    assert "stays on V1" in text, text[-600:]
    text = hear("Rounds complete.", 240)  # the step starting, the shot and the end can all come in one wake
    assert "Now fire mission, 1 HE at grid 028 020." in text, text[-600:]

    # A gunner who's down isn't a gunner, though he's alive and still in his seat. Mid-mission, then from the start.
    fire(at="028 020", rounds=8, guns=["V1"])
    hear("Shot,", 60)
    in_game(harness, 'gunner (brmh_cmd_vehicles get "V1") setUnconscious true; true')
    text = hear("fired, no gunner on V1.", 40)
    assert "Gunner down on V1" in text, text[-500:]
    fire(at="028 020", rounds=1, guns=["V1"])
    hear("Unable, no gunner on V1.", 30)

    # And dead. "Gunner down" was said when he went down, and isn't said twice.
    in_game(harness, 'gunner (brmh_cmd_vehicles get "V1") setDamage 1; true')
    time.sleep(5)
    fire(at="028 020", rounds=1)
    hear("Unable, no gun crewed.", 30)
    fire(at="028 020", rounds=1, guns=["V1"])
    hear("Unable, no gunner on V1.", 30)
    return log


def play_fire_support(client: Client) -> list[str]:
    """A real fight with a mortar, by the commander's tools: scouts forward, a round to adjust, then fire for effect on
    the village. It doesn't try to win. It's to see what a fight sounds like, and what the rounds really do."""
    begin(client)
    client.tool("commander_order", to="Recon", legs=[{"type": "MOVE", "at": "041 037"}, {"type": "SENTRY"}])
    finish_turn(client, "Scouts forward")
    log = [heard(client, "In position", 120)]
    client.tool("commander_order", to="Hammer", legs=[{
        "type": "FIRE_MISSION", "at": "041 041", "rounds": 1, "observer": "Recon"}])
    log.append(heard(client, "Rounds complete", 60))
    time.sleep(35)  # for the observer's call, if it can see it land at all
    client.tool("commander_order", to="Hammer", legs=[{
        "type": "FIRE_MISSION", "at": "041 041", "rounds": 8, "radius": 60}])
    log.append(heard(client, "Rounds complete", 60))
    client.tool("commander_order", to="Hammer", legs=[{
        "type": "FIRE_MISSION", "at": "041 041", "rounds": 7, "radius": 60}])
    log.append(heard(client, "Rounds complete", 60))
    time.sleep(40)
    client.tool("commander_ask", to="Hammer", topics=["ammo"])
    return log


def play_motor_march(client: Client) -> list[str]:
    """Two fire teams board Hunters, drive 2.5 km past the village, and get out, by the commander's tools alone."""
    harness = Harness()
    brief = begin(client)
    known = {vehicle["id"]: vehicle["type"] for vehicle in brief["vehicles"]}
    assert set(known) == {"V1", "V2"} and "Hunter" in known["V1"], known
    log = []
    for team, hunter in (("Alpha", "V1"), ("Bravo", "V2")):
        client.tool("commander_order", to=team, legs=[{"type": "MOUNT", "vehicle": hunter}])
    finish_turn(client, "Boarding")
    text = ""
    deadline = time.time() + 120
    while not (" on V1" in text and " on V2" in text):
        assert time.time() < deadline, f"the teams never boarded: {text[-500:]}"
        text += next_wake(client, 60)["content"]
        finish_turn(client, "Waiting to board")
    log.append(text)
    assert "didn't fit" not in text, text[-500:]

    for team in ("Alpha", "Bravo"):
        client.tool("commander_order", to=team, legs=[{"type": "MOVE", "at": "052 044"}])
    finish_turn(client, "Driving")
    started = time.time()

    # Told they were aboard, so they stay aboard: nobody climbs out when the order to drive comes.
    aboard = []
    for _ in range(10):
        aboard.append(in_game(harness, """
        ["V1", "V2"] apply {
            count crew (brmh_cmd_vehicles get _x)
        }
        """))
        time.sleep(2)
    print("ABOARD", aboard, flush=True)
    assert all(row == [4, 4] for row in aboard), aboard
    text = ""
    while not (text.count("Arrived") >= 2):
        assert time.time() - started < 420, f"the teams never arrived: {text[-800:]}"
        text += next_wake(client, 120)["content"]
        finish_turn(client, "Driving")
    log.append(text)
    print(f"DROVE IN {time.time() - started:.0f} s", flush=True)
    state = in_game(harness, """
    ["V1", "V2"] apply {
        private _hunter = brmh_cmd_vehicles get _x;
        [_x, round (_hunter distance2D [5250, 4450]), count crew _hunter, damage _hunter]
    }
    """)
    print("HUNTERS AT THE GRID", state, flush=True)
    assert all(row[1] < 200 and row[2] == 4 for row in state), state

    # Nobody gets out until told, and being there isn't enough to end the mission.
    assert not client.tool("commander_mission").get("ended"), "it ended with the teams still mounted"
    for team in ("Alpha", "Bravo"):
        client.tool("commander_order", to=team, legs=[{"type": "DISMOUNT"}])
    finish_turn(client, "Dismounting")
    text = ""
    deadline = time.time() + 90
    while "MISSION END" not in text:
        assert time.time() < deadline, f"the mission never ended: {text[-800:]}"
        text += next_wake(client, 60)["content"]
        if "MISSION END" not in text:
            finish_turn(client, "Waiting")
    log.append(text)
    assert "Objective achieved: Alpha and Bravo are on foot at grid 052 044." in text, text[-500:]
    assert "OBJECTIVE COMPLETE: Both teams on foot at grid 052 044. Higher command confirms" in text, text[-500:]
    assert text.index("OBJECTIVE COMPLETE") < text.index("MISSION END"), text[-500:]
    return log


def play_casevac(client: Client) -> list[str]:
    """The owner's plan, step by step, by the commander's tools alone. Only the two men going down come from outside."""
    harness = Harness()
    begin(client)
    finish_turn(client, "Waiting")
    log: list[str] = []

    def hear(phrase, timeout=120, times=1):
        text, deadline = "", time.time() + timeout
        while text.count(phrase) < times:
            assert time.time() < deadline, f"never heard {phrase!r} {times}x: {text[-900:]}"
            text += heard(client, phrase, max(1, deadline - time.time()))
        log.append(text)
        return text

    def order(to, *legs):
        return client.tool("commander_order", to=to, legs=list(legs))

    def alpha_state():
        return in_game(harness, """
        private _group = brmh_cmd_stations get "Alpha";
        [count units _group, {alive _x} count units _group, {vehicle _x isNotEqualTo _x} count units _group,
         {lifeState _x isEqualTo "INCAPACITATED"} count units _group,
         round ((leader _group) distance2D [4050, 6050]), round ((brmh_cmd_vehicles get "V1") distance2D [4050, 6050])]
        """)

    # Two of six go down, by the scenario's own event.
    text = hear("Listed as C", 60, 2)
    assert "C1" in text and "C2" in text, text
    print("STATE two down", alpha_state(), flush=True)

    # The estimate goes by how the squad's really moving, which the order has just set: 1 km at 1.4 m/s, not 4.1.
    client.tool("commander_order", to="Angel", legs=[{"type": "MOVE", "at": "020 070"}], behaviour="AWARE",
                speed="LIMITED")
    hear("That's 1 km on foot, about 12 minutes.", 60)
    client.tool("commander_order", to="Angel", legs=[{"type": "HALT"}], behaviour="AWARE", speed="NORMAL")

    # Two healthy men carry them to the truck.
    order("Alpha", {"type": "CARRY", "casualties": ["C1", "C2"], "vehicle": "V1"})
    text = hear("'s loaded.", 200, 2)
    assert "Copy, carrying" in text and "Got " in text, text[-900:]
    print("STATE loaded", alpha_state(), flush=True)

    # The squad gets on after them, and goes to the rendezvous.
    order("Alpha", {"type": "MOUNT", "vehicle": "V1"})
    text = hear(" on V1.", 120)
    state = alpha_state()
    print("STATE mounted", state, flush=True)
    assert "didn't fit" not in text and state[2] == 6 and state[3] == 2, (text[-500:], state)
    order("Alpha", {"type": "MOVE", "at": "040 060"})

    # Meanwhile the medics get on theirs, go there, get off and set up.
    order("Angel", {"type": "MOUNT", "vehicle": "V2"})
    hear(" on V2.", 120)
    order("Angel", {"type": "MOVE", "at": "040 060"})
    text = hear("Arrived, grid 040 060", 300, 2)
    print("STATE at the rendezvous", alpha_state(), flush=True)
    order("Angel", {"type": "DISMOUNT"})
    hear("Off the vehicle", 60)
    order("Angel", {"type": "AID_POST", "at": "040 060"})
    text = hear("Listed as A1", 90)
    assert "Setting up the aid post." in text and "Aid post up, grid 04" in text, text[-500:]

    # The squad gets off, and gets its casualties off, and over to the post.
    order("Alpha", {"type": "DISMOUNT"})
    hear("Off the vehicle", 60)
    state = alpha_state()
    print("STATE squad off", state, flush=True)
    assert state[2] == 2, state  # the two casualties are still in their seats
    order("Alpha", {"type": "UNLOAD", "vehicle": "V1"})
    hear("'s off V1.", 40, 2)
    state = alpha_state()
    print("STATE unloaded", state, flush=True)
    assert state[2] == 0 and state[3] == 2 and state[0] == 6, state  # still his squad's
    order("Alpha", {"type": "CARRY", "casualties": ["C1", "C2"], "at": "A1"})
    hear("Set ", 200, 2)
    order("Alpha", {"type": "SENTRY", "at": "040 060"})

    # The medics treat them, at the post's speed.
    placed = in_game(harness, """
    ((units (brmh_cmd_stations get "Alpha")) select { lifeState _x isEqualTo "INCAPACITATED" }) apply {
        [name _x, round (_x distance2D (brmh_cmd_posts # 0)), [_x] call brmh_cmd_fnc_atFacility]
    }
    """)
    print("AT THE POST", placed, flush=True)
    assert all(row[2] for row in placed), placed
    started = time.time()
    order("Angel", {"type": "TREAT", "casualties": ["C1", "C2"]})
    text = hear("'s back up.", 180, 2)
    assert "Treating " in text, text[-500:]
    took = time.time() - started
    print(f"TREATED both in {took:.0f} s", flush=True)
    assert took < 60, took
    assert text.count("Can't get to") == 0, text[-500:]
    state = alpha_state()
    print("STATE treated", state, flush=True)
    assert state[0] == 6 and state[1] == 6 and state[3] == 0, state
    time.sleep(15)

    # The squad mounts back up, all six, and goes back.
    order("Alpha", {"type": "MOUNT", "vehicle": "V1"})
    text = hear(" on V1.", 150)
    state = alpha_state()
    print("STATE back on", state, flush=True)
    assert state[2] == 6, (state, text[-400:])
    tent = """brmh_cmd_posts apply {
        [alive _x, round (damage _x * 100) / 100, round (_x distance2D (brmh_cmd_vehicles get 'V1'))]
    }"""
    print("POST before driving", in_game(harness, tent), flush=True)
    order("Alpha", {"type": "MOVE", "at": "070 060"})
    time.sleep(10)
    after = in_game(harness, tent)
    print("POST after driving off", after, flush=True)
    assert after[0][0], after  # it was flattened by the truck, before
    hear("Arrived, grid 070 060", 300)
    order("Alpha", {"type": "DISMOUNT"})
    text = ""
    deadline = time.time() + 90
    while "MISSION END" not in text:
        assert time.time() < deadline, text[-600:]
        text += next_wake(client, 60)["content"]
        if "MISSION END" not in text:
            finish_turn(client, "Waiting")
    assert "OBJECTIVE COMPLETE" in text, text[-500:]
    log.append(text)
    errors = harness.events(since=0, kinds=["err"]).get("events", [])
    assert not errors, [str(e.get("text"))[:200] for e in errors[:4]]
    return log


def play_casevac_chained(client: Client) -> list[str]:
    """The owner's plan again, as whole tasks: one order per job, and nobody woken to give the next step."""
    harness = Harness()
    begin(client)
    finish_turn(client, "Waiting")
    log: list[str] = []
    so_far = [""]

    def hear(phrase, timeout=120, times=1):
        """Two squads talk at once here, so one line can arrive while waiting for another: all of it counts."""
        deadline = time.time() + timeout
        while so_far[0].count(phrase) < times:
            assert time.time() < deadline, f"never heard {phrase!r} {times}x: {so_far[0][-1500:]}"
            so_far[0] += heard(client, phrase, max(1, deadline - time.time()))
        return so_far[0]

    def order(to, *legs):
        return client.tool("commander_order", to=to, legs=list(legs))

    mount_v1, mount_v2 = {"type": "MOUNT", "vehicle": "V1"}, {"type": "MOUNT", "vehicle": "V2"}
    to_rv, off = {"type": "MOVE", "at": "040 060"}, {"type": "DISMOUNT"}

    # Cancelled partway, and it says what it won't now do.
    order("Angel", mount_v2, to_rv, off)
    hear("Copy, mounting V2, then moving to grid 040 060, then getting off.", 30)
    order("Angel", {"type": "HALT"})
    hear("Dropping the rest: moving to grid 040 060, then getting off.", 30)
    boarding = in_game(harness, """
    private _group = brmh_cmd_stations get "Angel";
    [count (_group getVariable ["brmh_cmd_mountList", []]), {vehicle _x isNotEqualTo _x} count units _group]
    """)
    time.sleep(12)
    aboard = in_game(harness, """{vehicle _x isNotEqualTo _x} count units (brmh_cmd_stations get "Angel")""")
    print("HALTED, list and aboard", boarding, "then aboard", aboard, flush=True)
    assert boarding[0] == 0 and aboard == boarding[1], (boarding, aboard)  # nobody else climbs in

    # A squad order takes back the men walking to their seats, and says so.
    order("Angel", mount_v2)
    hear("Copy, mounting V2.", 30)
    order("Angel", {"type": "MOVE", "at": "020 061"})
    hear("Stopped getting on V2.", 30)
    boarding = in_game(harness, """count ((brmh_cmd_stations get "Angel") getVariable ["brmh_cmd_mountList", []])""")
    assert boarding == 0, boarding

    text = hear("Listed as C", 60, 2)
    assert "C1" in text and "C2" in text, text

    # Each squad gets its whole job in one order.
    order("Angel", mount_v2, to_rv, off, {"type": "AID_POST", "at": "040 060"})
    order("Alpha", {"type": "CARRY", "casualties": ["C1", "C2"], "vehicle": "V1"}, mount_v1, to_rv, off,
          {"type": "UNLOAD", "vehicle": "V1"}, {"type": "CARRY", "casualties": ["C1", "C2"], "at": "040 060"})
    text = hear("then getting our casualties off V1", 30)
    assert "At least" in text, text
    hear("Aid post up", 300)
    hear("Now mounting V1.", 300)
    hear("Now moving to grid 040 060.", 120)
    hear("'s off V1.", 300, 2)
    hear("Set ", 200, 2)

    state = in_game(harness, """
    private _group = brmh_cmd_stations get "Alpha";
    [{lifeState _x isEqualTo "INCAPACITATED"} count units _group, {vehicle _x isNotEqualTo _x} count units _group,
     round ((brmh_cmd_vehicles get "V1") distance2D [4050, 6050])]
    """)
    print("STATE delivered to the post", state, flush=True)
    assert state[0] == 2 and state[1] == 0 and state[2] < 150, state

    order("Angel", {"type": "TREAT", "casualties": ["C1", "C2"]})
    hear("'s back on their feet", 200, 2)

    # And back up the road. All six, on foot, at the objective, is what ends it.
    order("Alpha", mount_v1, {"type": "MOVE", "at": "070 060"}, off)
    text = hear("MISSION END", 420)  # a long quiet drive: nothing needs saying until it's there
    assert "OBJECTIVE COMPLETE" in text, text[-500:]
    log.append(so_far[0])
    errors = harness.events(since=0, kinds=["err"]).get("events", [])
    assert not errors, [str(e.get("text"))[:200] for e in errors[:4]]
    return log


def play_casevac_village(client: Client) -> list[str]:
    """Carrying and treating while squads are busy among buildings. Each scene is somewhere two of the game's machines
    once disagreed about who a man belonged to."""
    harness = Harness()
    brief = begin(client)
    finish_turn(client, "Waiting")
    so_far = [""]

    def hear(phrase, timeout=120, times=1):
        deadline = time.time() + timeout
        while so_far[0].count(phrase) < times:
            assert time.time() < deadline, f"never heard {phrase!r} {times}x: {so_far[0][-1500:]}"
            so_far[0] += heard(client, phrase, max(1, deadline - time.time()))
        return so_far[0]

    def order(to, *legs):
        return client.tool("commander_order", to=to, legs=list(legs))

    def knock(callsign):
        return in_game(harness, f"""
        private _group = brmh_cmd_stations get "{callsign}";
        private _men = ((units _group) - [leader _group]) select {{
            lifeState _x isNotEqualTo "INCAPACITATED" and {{ not (_x getVariable ["brmh_cmd_busy", false]) }}
        }};
        [_men # 0, true, 0, false] call ace_medical_fnc_setUnconscious;
        name (_men # 0)
        """)

    def listed(name):
        return next(row["id"] for row in client.tool("commander_mission")["casualties"] if row["name"] == name)

    def carriers_rooms():
        """Each carrier's deadline for the room he was last given. It may be left over from before he was picked."""
        return dict(in_game(harness, """
        ((units (brmh_cmd_stations get "Alpha")) select { _x getVariable ["brmh_cmd_busy", false] }) apply {
            [name _x, _x getVariable ["brmh_cmd_clearBy", 0]]
        }
        """))

    # Clearing hands every man a room, and used to hand one to a man carrying someone too.
    biggest = sorted(brief["buildings"], key=lambda b: -b["positions"])[:2]
    order("Alpha", {"type": "CLEAR", "at": [b["id"] for b in biggest]})
    hear("Copy, checking", 30)
    time.sleep(8)
    who = knock("Alpha")
    hear(f"{who}'s down", 40)
    order("Alpha", {"type": "CARRY", "casualties": [listed(who)], "at": "038 038"})
    hear(f"Copy, carrying {who}", 40)
    before = carriers_rooms()
    assert before, "nobody's carrying"
    for _ in range(8):
        time.sleep(4)
        now = carriers_rooms()
        sent = [name for name, by in now.items() if name in before and by != before[name]]
        assert sent == [], f"carriers handed another room to clear: {sent}"
    hear(f"Set {who} down.", 300)

    # DEFEND switches off each man's pathing as he reaches his post, which used to leave a carrier unable to walk.
    order("Alpha", {"type": "DEFEND", "at": "040 041", "radius": 80})
    hear("Copy, defending", 30)
    time.sleep(60)
    who = knock("Alpha")
    hear(f"{who}'s down", 40)
    order("Alpha", {"type": "CARRY", "casualties": [listed(who)], "at": "038 038"})
    # Slow, not stuck: reaching a man at his post among the buildings, then 400 m or so at a carrier's pace.
    text = hear(f"Set {who} down.", 600)
    assert f"Can't get to {who}" not in text, text[-600:]

    # Treating and carrying the same man: the medics wait until he's set down, rather than chase him.
    third = knock("Bravo")
    hear(f"{third}'s down", 40)
    ids = [row["id"] for row in client.tool("commander_mission")["casualties"]]
    order("Medics", {"type": "TREAT", "casualties": ids})
    order("Bravo", {"type": "CARRY", "casualties": [listed(third)], "at": "039 038"})
    for _ in range(15):
        time.sleep(4)
        chased = in_game(harness, """
        private _carried = brmh_cmd_carries apply { _x get "casualty" };
        private _chased = [];
        {
            {
                if ((_x get "casualty") in _carried) then { _chased pushBack name (_x get "casualty") };
            } forEach (_x get "jobs");
        } forEach brmh_cmd_treats;
        _chased
        """)
        assert chased == [], f"medics treating a man being carried: {chased}"
    hear("'s back up.", 400, len(ids))
    errors = harness.events(since=0, kinds=["err"]).get("events", [])
    assert not errors, [str(e.get("text"))[:200] for e in errors[:4]]
    return [so_far[0]]


def play_casevac_cases(client: Client) -> list[str]:
    """What the plan doesn't touch: treating in the field, a medical vehicle, nobody to go back to, a leader waking, a
    man left behind, a carry while the squad is on the move, and the things that fail."""
    harness = Harness()
    begin(client)
    finish_turn(client, "Waiting")
    log: list[str] = []

    def hear(phrase, timeout=120, times=1):
        text, deadline = "", time.time() + timeout
        while text.count(phrase) < times:
            assert time.time() < deadline, f"never heard {phrase!r} {times}x: {text[-900:]}"
            text += heard(client, phrase, max(1, deadline - time.time()))
        log.append(text)
        return text

    def order(to, *legs):
        return client.tool("commander_order", to=to, legs=list(legs))

    def knock(callsign, how_many=1, leader=False):
        return in_game(harness, f"""
        missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
        private _group = brmh_cmd_stations get "{callsign}";
        private _men = (units _group) - [leader _group];
        if ({str(leader).lower()}) then {{ _men = [leader _group]; }};
        private _chosen = (_men select {{ lifeState _x isNotEqualTo "INCAPACITATED" }}) select [0, {how_many}];
        {{ [_x, true, 0, false] call ace_medical_fnc_setUnconscious; }} forEach _chosen;
        _chosen apply {{ name _x }}
        """)

    def listed(name):
        return next(row["id"] for row in client.tool("commander_mission")["casualties"] if row["name"] == name)

    # No medic in the squad: refused aloud.
    who = knock("Bravo")[0]
    hear("Listed as C", 40)
    order("Bravo", {"type": "CARRY", "at": "051 060"})
    hear("Set ", 150)
    # The field, at the field's speed, by a medic team on foot.
    near = in_game(harness, f"""
    private _man = (units (brmh_cmd_stations get "Bravo")) select {{ name _x isEqualTo "{who}" }} select 0;
    {{ _x setPosATL ((getPosATL _man) getPos [15 + random 10, random 360]); }}
        forEach units (brmh_cmd_stations get "Medics");
    mapGridPosition _man
    """)
    print("medics moved next to him at", near, flush=True)
    time.sleep(3)
    started = time.time()
    order("Medics", {"type": "TREAT", "casualties": [listed(who)]})
    hear("'s back up.", 120)
    took = time.time() - started
    print(f"FIELD treated in {took:.0f} s", flush=True)
    assert took >= 20, took  # field_s is 25, and the post was 10

    # Into a medical vehicle, and treated aboard it, faster, without coming off.
    who = knock("Bravo")[0]
    hear("Listed as C", 40)
    order("Bravo", {"type": "CARRY", "casualties": [listed(who)], "vehicle": "V2"})
    hear("'s loaded.", 200)
    aboard = in_game(harness, """
    (crew (brmh_cmd_vehicles get "V2")) apply { [name _x, lifeState _x] }
    """)
    print("ABOARD V2", aboard, flush=True)
    in_game(harness, """
    {
        _x setPosATL ((brmh_cmd_vehicles get "V2") getPos [10 + random 5, random 360]);
    } forEach units (brmh_cmd_stations get "Medics");
    true
    """)
    time.sleep(3)
    started = time.time()
    order("Medics", {"type": "TREAT", "casualties": [listed(who)]})
    hear("'s back up.", 120)
    took = time.time() - started
    print(f"MEDICAL VEHICLE treated in {took:.0f} s", flush=True)
    assert took < 32, took  # facility_s is 10, and he has up to 15 m to walk first. Field treatment took 33 to 37 s
    in_game(harness, f"""
    private _man = (units (brmh_cmd_stations get "Bravo")) select {{ name _x isEqualTo "{who}" }} select 0;
    if (vehicle _man isNotEqualTo _man) then {{ [_man] call brmh_cmd_fnc_getOff; }};
    true
    """)

    # A treated man whose squad's gone joins whoever treated him.
    lone = in_game(harness, """
    private _group = brmh_cmd_stations get "Lone";
    private _men = units _group;
    { _x setDamage 1; } forEach (_men select [1, 3]);
    missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
    [_men # 0, true, 0, false] call ace_medical_fnc_setUnconscious;
    { _x setPosATL ((getPosATL (_men # 0)) getPos [15 + random 5, random 360]); }
        forEach units (brmh_cmd_stations get "Medics");
    name (_men # 0)
    """)
    time.sleep(6)  # only the medics can see him: his squad's gone, and there's nobody to say
    hear(f"Found {lone} down", 30)
    order("Medics", {"type": "TREAT"})
    hear("with us now", 240)  # a teleport above doesn't always take, and then he runs it, 600 m at 4 m/s
    state = in_game(harness, """
    [count units (brmh_cmd_stations get "Medics"), count units (brmh_cmd_stations get "Lone")]
    """)
    print("JOINED [medics, lone]", state, flush=True)
    assert state[0] == 4, state  # three medics, and him

    # A leader down: command passes, the squad obeys, and it stays with the new man when he wakes.
    leader = knock("Bravo", leader=True)[0]
    time.sleep(8)
    order("Bravo", {"type": "MOVE", "at": "056 060"})
    hear("Copy, moving", 40)
    time.sleep(15)
    in_game(harness, f"""
    private _man = (units (brmh_cmd_stations get "Bravo")) select {{ name _x isEqualTo "{leader}" }} select 0;
    [_man] call ace_medical_fnc_fullHeal;
    true
    """)
    time.sleep(10)
    who_leads = in_game(harness, 'name leader (brmh_cmd_stations get "Bravo")')
    print("LEADER after waking", leader, who_leads, flush=True)
    assert who_leads != leader, who_leads
    hear("Arrived, grid 056 060", 180)

    # A carry while the rest of the squad is moving: the bearer isn't dragged off by the squad's orders.
    who = knock("Bravo")[0]
    hear("Listed as C", 40)
    order("Bravo", {"type": "MOVE", "at": "054 063"})
    time.sleep(3)
    order("Bravo", {"type": "CARRY", "casualties": [listed(who)], "at": "056 062"})
    hear("Set ", 200)

    # The newest order wins. Called off partway: he's put down where he is, and his bearer goes back to the squad.
    order("Bravo", {"type": "CARRY", "casualties": [listed(who)], "at": "054 063"})
    hear(f"Got {who}, on the way", 120)
    order("Bravo", {"type": "HOLD", "at": "054 063"})
    hear(f"Put {who} down.", 30)
    state = in_game(harness, f"""
    private _men = units (brmh_cmd_stations get "Bravo");
    private _him = (_men select {{ name _x isEqualTo "{who}" }}) # 0;
    [{{ (_x get "state") isNotEqualTo "done" }} count brmh_cmd_carries, str attachedTo _him,
     {{ _x getVariable ["brmh_cmd_busy", false] }} count _men, _him getVariable ["brmh_cmd_handled", ""],
     lifeState _him]
    """)
    print("CALLED OFF", state, flush=True)
    assert state == [0, "<NULL-object>", 0, "", "INCAPACITATED"], state

    # Picked up again, then told to take him somewhere else on the way there.
    order("Bravo", {"type": "CARRY", "casualties": [listed(who)], "at": "054 061"})
    hear(f"Got {who}, on the way", 120)
    order("Bravo", {"type": "CARRY", "casualties": [listed(who)], "at": "055 063"})
    hear(f"Set {who} down.", 200)
    away = in_game(harness, f"""
    private _him = (units (brmh_cmd_stations get "Bravo")) select {{ name _x isEqualTo "{who}" }};
    round ((_him # 0) distance2D [5550, 6350])
    """)
    print("REDIRECTED, metres from the new place", away, flush=True)
    assert away <= 15, away

    # Medics stop treating, and stop building.
    order("Medics", {"type": "TREAT", "casualties": [listed(who)]})
    time.sleep(5)
    order("Medics", {"type": "HOLD", "at": "052 058"})
    hear(f"Stopped treating {who}.", 30)
    order("Medics", {"type": "AID_POST", "at": "052 058"})
    time.sleep(3)
    order("Medics", {"type": "HOLD", "at": "052 058"})
    hear("Stopped setting up the aid post.", 30)
    state = in_game(harness, """
    [count brmh_cmd_posts, count brmh_cmd_builds, count brmh_cmd_treats,
     {_x getVariable ["brmh_cmd_busy", false]} count units (brmh_cmd_stations get "Medics")]
    """)
    print("MEDICS CALLED OFF", state, flush=True)
    assert state == [0, 0, 0, 0], state

    # A full count isn't everyone being there. His squad goes off, he's treated, and he's a long walk from it.
    order("Bravo", {"type": "MOVE", "at": "050 060"})
    hear(f"We've left {who}", 240)
    order("Medics", {"type": "TREAT", "casualties": [listed(who)]})
    hear(f"{who}'s back on their feet, about", 300)
    answer = client.tool("commander_ask", to="Bravo", topics=["strength"])["replies"][0]["text"]
    print("STRENGTH", answer, flush=True)
    assert f"Not with us: {who}, about" in answer, answer
    hear(f"{who}'s back with the squad.", 300)
    answer = client.tool("commander_ask", to="Bravo", topics=["strength"])["replies"][0]["text"]
    print("STRENGTH", answer, flush=True)
    assert "Not with us" not in answer, answer

    # Told to treat a man still on a truck, the medics wait for him to come off, and then do it.
    who = knock("Bravo")[0]
    hear("Listed as C", 40)
    order("Bravo", {"type": "CARRY", "casualties": [listed(who)], "vehicle": "V1"})
    hear(f"{who}'s loaded.", 200)
    order("Medics", {"type": "TREAT", "casualties": [listed(who)]})
    hear("We'll treat them when they're off.", 30)
    time.sleep(10)
    state = in_game(harness, """
    [count brmh_cmd_treats, {_x getVariable ["brmh_cmd_busy", false]} count units (brmh_cmd_stations get "Medics")]
    """)
    print("WAITING", state, flush=True)
    assert state == [1, 0], state
    order("Bravo", {"type": "MOVE", "at": "049 062"})
    hear("Arrived, grid", 120)
    order("Bravo", {"type": "UNLOAD", "vehicle": "V1"})
    hear(f"{who}'s off V1.", 30)
    hear(f"{who}'s back up.", 300)

    # A chain can't hang on a man who dies while waiting his turn. The medics are the ones who say so.
    who = knock("Bravo")[0]
    hear("Listed as C", 40)
    one = listed(who)
    client.tool("commander_order", to="Medics", legs=[{"type": "TREAT", "casualties": [one]},
                                                      {"type": "MOVE", "at": "052 058"}])
    in_game(harness, f"""
    private _him = (units (brmh_cmd_stations get "Bravo")) select {{ name _x isEqualTo "{who}" }};
    (_him # 0) setDamage 1;
    true
    """)
    text = hear("Now moving to grid 052 058.", 60)  # the two lines come together
    assert f"{who}'s dead." in text, text[-600:]

    # Left behind.
    who = knock("Charlie")[0]
    hear("Listed as C", 40)
    order("Charlie", {"type": "MOVE", "at": "065 040"})
    hear(f"We've left {who}", 120)
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
    # Clearing is only sent once a squad has finished searching, and the fight can be won before it reports a room.
    won = "Objective achieved" in text
    assert "checked, " in text or not clearing or won, "no squad reported checking a building"
    gridded = [line for line in text.splitlines() if "Contact" in line and "grid" in line.lower()]
    assert not gridded, f"contact reports stating a grid: {gridded[:3]}"
    return seen


def play_cas(client: Client) -> list[str]:
    """Close air support on a real game: the pilot flies to the grid, attacks what he finds, and says so."""
    harness = Harness()
    begin(client)
    seen, sorties, deadline = [], 0, time.time() + 13 * 60
    while time.time() < deadline and sorties < 3:
        sorties += 1
        client.tool("commander_order", to="Hawg", legs=[{"type": "CAS", "at": "037 024", "radius": 200}])
        finish_turn(client, f"Sortie {sorties}")
        while time.time() < deadline:
            wake = next_wake(client, 300)
            seen.append(wake["content"])
            if sorties == 1 and "Engaging" in wake["content"]:
                snap(harness, "cas engaging")
            finish_turn(client, "Waiting")
            if "MISSION END" in wake["content"] or "returning to hold" in wake["content"]:
                break
        if "MISSION END" in seen[-1]:
            break
    text = chr(10).join(seen)
    assert "Hawg: Copy, grid 037 024, on the way." in text, text[-2000:]
    assert "Hawg: Over grid 037 024, looking." in text
    assert "returning to hold" in text or "MISSION END" in text
    return seen


def play_stratis_clear(client: Client) -> list[str]:
    """A squad going through buildings it can't all get into says which, and never calls those checked."""
    brief = begin(client)
    ids = [building["id"] for building in brief["buildings"]]
    print("    buildings:", [(b["id"], b["type"]) for b in brief["buildings"]], flush=True)
    client.tool("commander_order", to="Alpha", legs=[{"type": "CLEAR", "at": "032 029", "radius": 120}])
    finish_turn(client, "Clearing")
    seen, deadline = [], time.time() + 12 * 60
    while time.time() < deadline:
        wake = next_wake(client, 300)
        seen.append(wake["content"])
        finish_turn(client, "Waiting")
        if "Finished checking" in wake["content"] or "Couldn't get into any" in wake["content"]:
            break
    text = chr(10).join(seen)
    cargo = [b["id"] for b in brief["buildings"] if "Cargo House" in b["type"]]
    assert any(f"Couldn't get into {building}" in text for building in cargo), "no cargo house reported as shut"
    assert len(ids) >= 3
    return seen


def play_stratis(client: Client) -> list[str]:
    """Real ground: the map's terrain, named places and the ground tool, then the same fight as the village, uphill."""
    harness = Harness()
    brief = begin(client)
    places = {place["name"]: place for place in brief.get("places", [])}
    print("    places:", [(name, place["grid"]) for name, place in places.items()], flush=True)
    assert places["Camp Maxwell"]["grid"] == "032 029" and places["Agios Ioannis"]["grid"] == "030 021", places
    assert brief["buildings"], "no numbered buildings at Camp Maxwell"
    camp = client.tool("commander_ground", at="O1")["text"]
    start = client.tool("commander_ground", at="030 021")["text"]
    view = client.tool("commander_ground", at="030 021", to="O1")["text"]
    print(f"    ground at O1: {camp}", f"at the start: {start}", f"sight: {view}", sep="\n    ", flush=True)
    assert "Camp Maxwell" in camp and "Agios Ioannis" in start and "Trees and buildings" in view
    save_map(client, "stratis_start")
    save_map(client, "stratis_wide", radius=1500)
    save_map(client, "stratis_camp", center="O1", radius=250)
    client.tool("commander_order", to="Recon", legs=[{"type": "MOVE", "at": "031 026"}], behaviour="STEALTH")
    for callsign in ("Alpha", "Bravo"):
        client.tool("commander_schedule", after="0:30", do={"order": {
            "to": callsign, "legs": [{"type": "SEARCH", "at": "O1", "radius": 150}], "speed": "FULL"}})
    client.tool("commander_schedule", every="2:00", do={"wake": "Regular check"})
    finish_turn(client, "Recon forward, the squads at 0:30")
    seen, clearing, deadline = [], set(), time.time() + 30 * 60
    while time.time() < deadline:
        wake = next_wake(client, 300)
        seen.append(wake["content"])
        if "MISSION END" in wake["content"]:
            finish_turn(client, "Over")
            break
        if len(seen) == 8:
            snap(harness, "stratis mid battle")
        for callsign in ("Alpha", "Bravo"):
            if callsign not in clearing and (f"{callsign}: Finished searching" in wake["content"]
                                             or f"{callsign}: Not making progress" in wake["content"]):
                clearing.add(callsign)
                client.tool("commander_order", to=callsign, legs=[{"type": "CLEAR", "at": "O1", "radius": 150}])
                print(f"    {callsign} ordered to clear", flush=True)
        finish_turn(client, "Read the traffic")
    save_map(client, "stratis_end")
    text = chr(10).join(seen)
    assert "Contact," in text, "no contact report in the whole battle"
    gridded = [line for line in text.splitlines() if "Contact" in line and "grid" in line.lower()]
    assert not gridded, f"contact reports stating a grid: {gridded[:3]}"
    return seen


def run(name: str, scenario: str, mode: str | None, play, watch: bool = False) -> None:
    print(f"\n========== {name} ==========", flush=True)
    harness = Harness()
    # LIVE_NO_WATCH=1: nobody's watching, so don't open a game window.
    # LIVE_WATCH=1 opens one to watch a battle that wouldn't usually have one.
    wanted = (watch or os.environ.get("LIVE_WATCH")) and not os.environ.get("LIVE_NO_WATCH")
    state, needs = harness.state(), scenario_mod.load(scenario).mission
    if state is not None and state.mission != needs:  # this run's own game, left up by the battle before
        harness.stop()
    # Only this battle's errors count: a reused game still holds earlier ones, from other battles or spikes.
    since = harness.bridge().cursor() if harness.state() is not None else 0
    started = operator.start(scenario, mode, harness, watch=bool(wanted))
    print(json.dumps({k: v for k, v in started.items() if k != "launch"}), flush=True)
    client = Client()
    try:
        play(client)
    finally:
        client.close()
    print(f"\n--- AFTER ACTION: {name}\n{operator.aar(harness.home)}", flush=True)
    print(json.dumps(operator.status(harness.home), indent=1), flush=True)
    errors = harness.events(since=since, kinds=["err"], limit=0).get("events", [])
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
               ("fire support", "village_with_mortar", "hold", play_fire_support),
               ("motor march", "motor_march", "hold", play_motor_march),
               ("casevac plan", "casevac_rv", "hold", play_casevac),
               ("casevac cases", "casevac_cases", "hold", play_casevac_cases),
               ("casevac chained", "casevac_rv", "hold", play_casevac_chained),
               ("casevac village", "casevac_village", "hold", play_casevac_village),
               ("combat: take the village", "take_the_village", "hold", play_village, True),
               ("stratis: Camp Maxwell", "stratis_maxwell", "hold", play_stratis),
               ("stratis: clearing the camp", "stratis_clear_check", "hold", play_stratis_clear),
               ("stratis: close air support", "stratis_cas", "hold", play_cas)]
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
