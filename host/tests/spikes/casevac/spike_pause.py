"""The demo's scene 3 failed for a person who paused before it, and passes headless with no pause. Does the pause matter?
Scene 3's setup each time, with a wait before the carry starts, in which ACE's AI medic is free to act.
"""
import sys
import time
from pathlib import Path

from spike_ace_lib import game, run, show

from arma_harness.commander.operator import load_sqf

sys.path.insert(0, str(Path(__file__).parents[2]))

START = [4200, 4110, 0]
SETUP = """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
brmh_fnc_people = {
    params ["_medicAt", "_hurtAt"];
    private _group = createGroup [west, false];
    private _medic = _group createUnit ["B_medic_F", _medicAt, [], 0, "CAN_COLLIDE"];
    private _hurt = _group createUnit ["B_Soldier_F", _hurtAt, [], 0, "CAN_COLLIDE"];
    _group selectLeader _medic;
    [_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
    [_medic, _hurt]
};
true
"""
READ = """
private _m = brmh_pair # 0;
private _h = brmh_pair # 1;
[round (_m distance2D brmh_from), round ((_m distance _h) * 10) / 10, round speed _m, currentCommand _m, unitReady _m,
 animationState _m, brmh_carry_now get "state", brmh_carry_now get "result", _m getVariable ["ace_medical_ai_healQueue", "none"],
 expectedDestination _m # 1]
"""


def trial(harness, pause):
    print(f"\n=== A pause of {pause} s", flush=True)
    inside = run(harness, """
    private _house = nearestObject [[4150, 4130, 0], "Land_i_Stone_HouseBig_V2_F"];
    ((_house buildingPos -1) select {(_x # 2) < 1}) # 0
    """)
    run(harness, f"""
    brmh_from = {START};
    brmh_pair = [{START}, [{inside[0]}, {inside[1]}, 0]] call brmh_fnc_people;
    brmh_carry_now = createHashMapFromArray [["state", "waiting"], ["result", ""]];
    true
    """)
    time.sleep(pause)
    show("  after the pause", run(harness, READ))
    run(harness, "brmh_carry_now = [brmh_pair # 0, brmh_pair # 1, [4200, 4090, 0]] call brmh_cmd_fnc_startCarry; true")
    begun = time.time()
    while time.time() - begun < 90:
        time.sleep(5)
        row = run(harness, READ)
        print(f"  {time.time() - begun:3.0f}s moved {row[0]:3d}, {row[1]:5.1f} from body, speed {row[2]:2d}, {row[3]:5}, "
              f"ready {row[4]}, {row[5][:28]}, {row[6]} {row[7]}, queue {row[8]}, {row[9]}", flush=True)
        if row[6] in ("carrying", "done"):
            break
    run(harness, """
    {
        if (not isNil "brmh_carry_now" and {"dummy" in brmh_carry_now}) then {deleteVehicle (brmh_carry_now get "dummy")};
        deleteVehicle _x;
    } forEach brmh_pair;
    brmh_cmd_carries = [];
    true
    """)


def main():
    harness = game()
    run(harness, load_sqf("commander_boot.sqf"))
    run(harness, SETUP)
    show("ace_medical_ai_enabledFor", run(harness, "ace_medical_ai_enabledFor"))
    for pause in (3, 12, 12, 25, 40, 40, 60):
        trial(harness, pause)
    errors = harness.events(since=0, kinds=["err"]).get("events", [])
    print("\nscript errors", len(errors), [str(e.get("text"))[:160] for e in errors[:4]], flush=True)
    harness.stop()
    print("done", flush=True)


if __name__ == "__main__":
    main()
