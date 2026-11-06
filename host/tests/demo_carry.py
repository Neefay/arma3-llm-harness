"""A demo of medics carrying casualties, to watch in a game window. No commander: it's only the carry.

    host\\.venv\\Scripts\\python.exe host\\tests\\demo_carry.py          a game window, and it waits for you to look
    host\\.venv\\Scripts\\python.exe host\\tests\\demo_carry.py --check  headless: fails if a scene goes wrong

It boots its own game with ACE. Each scene is announced in the window's chat and in this terminal, with who to look for.
In the spectator, pick the medic from the list on the left, or fly to the grid.
"""
from __future__ import annotations

import json
import sys
import time

from arma_harness.commander.operator import load_sqf
from arma_harness.harness import Harness

CHECK = "--check" in sys.argv

SETUP = """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
brmh_demo_units = [];
brmh_demo_fnc_people = {
    params ["_medicAt", "_hurtAt"];
    private _group = createGroup [west, false];
    private _medic = _group createUnit ["B_medic_F", _medicAt + [0], [], 0, "CAN_COLLIDE"];
    private _hurt = _group createUnit ["B_Soldier_F", _hurtAt + [0], [], 0, "CAN_COLLIDE"];
    _group selectLeader _medic;
    [_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
    brmh_demo_units append [_medic, _hurt];
    [_medic, _hurt]
};
true
"""
READ = """
params ["_carry"];
private _medic = _carry get "medic";
private _hurt = _carry get "casualty";
[_carry get "state", _carry get "result", round (_medic distance2D ([_carry] call brmh_cmd_fnc_carryPlace)),
 round (_hurt distance2D _medic), animationState _medic, animationState _hurt, str attachedTo _hurt,
 lifeState _hurt, typeOf vehicle _hurt, mapGridPosition _hurt]
"""


class Demo:
    def __init__(self):
        self.harness = Harness()
        self.harness.forget_dead_run()
        if self.harness.state() is not None:
            raise SystemExit("A game is already running. Close it first: arma-harness stop")
        print("Booting a game with ACE. This takes about a minute.", flush=True)
        self.harness.start(mission="commander_ace", client=not CHECK)
        time.sleep(8)
        self.run(load_sqf("commander_boot.sqf"))
        self.run(SETUP)
        self.failed: list[str] = []

    def run(self, code: str, timeout: float = 30):
        res = self.harness.exec(code, "server", timeout=timeout, strip=False)
        result = res["results"][0] if res.get("results") else res
        if not res.get("ok") or result.get("errors"):
            raise RuntimeError(json.dumps(result)[:1500])
        return result.get("r")

    def say(self, text: str) -> None:
        print(f"\n{text}", flush=True)
        self.run(f'{json.dumps(text)} remoteExec ["systemChat", 0]; true')

    def scene(self, title: str, medic_at, hurt_at, to: str, expect: str, during: str = "", limit: float = 180,
              check_wait: float = 0) -> None:
        names = self.run(f"brmh_scene = [{list(medic_at)}, {list(hurt_at)}] call brmh_demo_fnc_people; "
                         "[name (brmh_scene # 0), name (brmh_scene # 1), mapGridPosition (brmh_scene # 1)]")
        self.say(f"{title}: medic {names[0]} goes to {names[1]} at grid {names[2]}.")
        self.pause(check_wait)
        self.run(f"brmh_carry = [brmh_scene # 0, brmh_scene # 1, {to}] call brmh_cmd_fnc_startCarry; true")
        begun, last, did = time.time(), "", False
        while time.time() - begun < limit:
            state, result, left, apart, *rest = self.run(f"[brmh_carry] call {{ {READ} }}")
            line = f"  {time.time() - begun:3.0f}s {state:9} {left:4d} m to go, body {apart} m from medic"
            if state != last:
                print(line, flush=True)
                last = state
            if during and not did and state == "carrying" and time.time() - begun > 25:
                self.run(during)
                did = True
                print("  (done to it, for this scene)", flush=True)
            if state == "done":
                final = self.run(f"[brmh_carry] call {{ {READ} }}")
                print(f"  {time.time() - begun:3.0f}s finished: {result}. {json.dumps(final[4:])}", flush=True)
                if result != expect:
                    self.failed.append(f"{title}: wanted {expect!r}, got {result!r}")
                self.say(f"Finished: {result}.")
                return
            time.sleep(2)
        self.failed.append(f"{title}: still {last} after {limit} s")
        self.say("It ran out of time.")

    def pause(self, check_wait: float = 0) -> None:
        """A person always takes a while here. A check with no wait once passed while the demo failed for the first
        person to watch it."""
        if CHECK:
            time.sleep(check_wait)
        else:
            input("  Press Enter to start this scene. ")


def main() -> None:
    demo = Demo()
    if not CHECK:
        print("\nThe game window's open, in a free spectator camera. Wait until you can see the world.", flush=True)
    demo.scene("1. In the open", (4400, 3800), (4430, 3800), "[4430, 3700, 0]", "carried")
    demo.run('brmh_demo_hunter = createVehicle ["B_MRAP_01_F", [4110, 4090, 0], [], 0, "CAN_COLLIDE"]; true')
    demo.scene("2. Around a house, then into a Hunter", (4135, 4190), (4110, 4185), "brmh_demo_hunter", "loaded")
    inside = demo.run("""
    private _house = nearestObject [[4150, 4130, 0], "Land_i_Stone_HouseBig_V2_F"];
    private _spots = (_house buildingPos -1) select {(_x # 2) < 1};
    _spots # 0
    """)
    demo.scene("3. Out of a house", (4200, 4110), (inside[0], inside[1]), "[4200, 4090, 0]", "carried", check_wait=40)
    demo.scene("4. Stuck on the way: it finishes by the fallback", (4500, 3800), (4530, 3800), "[4530, 3750, 0]",
               "placed", during='(brmh_carry get "dummy") disableAI "MOVE"; true')
    demo.scene("5. The medic is killed on the way", (4600, 3800), (4630, 3800), "[4630, 3600, 0]", "medic down",
               during='(brmh_carry get "medic") setDamage 1; true')
    demo.scene("6. The casualty dies on the way", (4700, 3800), (4730, 3800), "[4730, 3600, 0]", "he died",
               during='(brmh_carry get "casualty") setDamage 1; true')
    errors = [e for e in demo.harness.events(since=0, kinds=["err"]).get("events", [])]
    print(f"\nScenes that went wrong: {demo.failed or 'none'}. Script errors: {len(errors)}", flush=True)
    for error in errors[:5]:
        print("  ", str(error.get("text"))[:200], "|", str(error.get("near"))[:140], flush=True)
    if not CHECK:
        input("That's the demo. Press Enter to close the game. ")
    demo.harness.stop()
    if CHECK and (demo.failed or errors):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
