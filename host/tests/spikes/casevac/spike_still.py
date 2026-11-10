"""With ACE's AI medic off, a medic ordered to a casualty in a house stood still with unitReady true. Why?"""
import time

from spike_ace_lib import game, run, show

from arma_harness.commander.operator import load_sqf

START = [4200, 4110, 0]
PEOPLE = """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
brmh_house = nearestObject [[4150, 4130, 0], "Land_i_Stone_HouseBig_V2_F"];
brmh_spots = (brmh_house buildingPos -1) select {(_x # 2) < 1};
brmh_fnc_people = {
    params ["_medicAt", "_hurtAt"];
    private _group = createGroup [west, false];
    private _medic = _group createUnit ["B_medic_F", _medicAt, [], 0, "CAN_COLLIDE"];
    private _hurt = _group createUnit ["B_Soldier_F", _hurtAt, [], 0, "CAN_COLLIDE"];
    _group selectLeader _medic;
    _hurt setPosATL _hurtAt;
    [_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
    [_medic, _hurt]
};
true
"""


def trial(harness, title, lying, go, wait=4):
    print(f"\n=== {title}", flush=True)
    run(harness, f"brmh_p = [{START}, {lying}] call brmh_fnc_people; true")
    time.sleep(wait)
    show("  body", run(harness, "[getPosATL (brmh_p # 1), animationState (brmh_p # 1)]"))
    run(harness, go)
    for _ in range(6):
        time.sleep(3)
        show("  [moved, to body, speed, command, ready, dest]", run(harness, f"""
        private _m = brmh_p # 0;
        [round (_m distance2D {START}), round (_m distance (brmh_p # 1)), round speed _m, currentCommand _m,
         unitReady _m, expectedDestination _m # 1]
        """))
    run(harness, "{deleteVehicle _x} forEach brmh_p; brmh_cmd_carries = []; true")


harness = game()
run(harness, load_sqf("commander_boot.sqf"))
run(harness, PEOPLE)
show("enabledFor", run(harness, "ace_medical_ai_enabledFor"))
spots = run(harness, "brmh_spots")
show("ground floor spots", spots)
AT_BODY = "(brmh_p # 0) doMove (getPosATL (brmh_p # 1)); true"
trial(harness, "As the pause spike: z 0, on the spot's x and y", [spots[0][0], spots[0][1], 0], AT_BODY)
trial(harness, "Standing on the spot itself", spots[0], AT_BODY)
trial(harness, "z 0, doMove to the spot, not the body", [spots[0][0], spots[0][1], 0],
      f"(brmh_p # 0) doMove {spots[0]}; true")
trial(harness, "z 0, doMove to just outside the door side", [spots[0][0], spots[0][1], 0],
      "(brmh_p # 0) doMove [4160, 4105, 0]; true")
trial(harness, "z 0, doMove after a wait of 20 s", [spots[0][0], spots[0][1], 0], AT_BODY, 20)
errors = harness.events(since=0, kinds=["err"]).get("events", [])
print("errors", len(errors), [str(e.get("text"))[:200] for e in errors[:4]], flush=True)
harness.stop()
print("done", flush=True)
