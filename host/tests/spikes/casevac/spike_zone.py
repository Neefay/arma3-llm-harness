"""Does a body in a bad spot break his group's planning? The body is put in the zone where a medic never moved."""
import time

from spike_ace_lib import game, run, show

BAD = [4147.5, 4128.6, 0.19]
GOOD = [4148.4, 4129.5, 0.19]
START = [4200, 4110, 0]
SETUP = """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
brmh_fnc_people = {
    params ["_lying"];
    private _group = createGroup [west, false];
    private _medic = _group createUnit ["B_medic_F", [4200, 4110, 0], [], 0, "CAN_COLLIDE"];
    private _hurt = _group createUnit ["B_Soldier_F", _lying, [], 0, "CAN_COLLIDE"];
    _group selectLeader _medic;
    _hurt setPosATL _lying;
    [_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
    [_medic, _hurt]
};
true
"""


def trial(harness, title, lying, before, go="(brmh_p # 0) doMove [4170, 4110, 0]; true"):
    print(f"\n=== {title}", flush=True)
    run(harness, f"brmh_p = [{lying}] call brmh_fnc_people; true")
    time.sleep(5)
    run(harness, f"(brmh_p # 1) setPosATL {lying}; true")
    time.sleep(1)
    if before:
        show("  before", run(harness, before))
    show("  body", run(harness, "getPosATL (brmh_p # 1)"))
    run(harness, go)
    row = None
    for _ in range(4):
        time.sleep(4)
        row = run(harness, f"""
        private _m = brmh_p # 0;
        [round (_m distance2D {START}), round speed _m, currentCommand _m, unitReady _m,
         group _m isEqualTo group (brmh_p # 1), name leader group _m, name _m]
        """)
    print("  [moved, speed, command, ready, same group, leader, medic]", row, flush=True)
    run(harness, "{deleteVehicle _x} forEach brmh_p; true")
    return row[0]


harness = game()
run(harness, SETUP)
results = {
    "good spot, in his group": trial(harness, "Good spot, in his group", GOOD, ""),
    "bad spot, in his group": trial(harness, "Bad spot, in his group", BAD, ""),
    "bad spot, in his group, again": trial(harness, "Bad spot, in his group, again", BAD, ""),
    "bad spot, body taken out of the group": trial(harness, "Bad spot, body taken out of the group", BAD,
                                                   "[brmh_p # 1] joinSilent createGroup [west, true]; true"),
    "bad spot, medic taken out of the group": trial(harness, "Bad spot, medic taken out of the group", BAD,
                                                    "[brmh_p # 0] joinSilent createGroup [west, true]; true"),
    "bad spot, body is leader-free, disableAI": trial(harness, "Bad spot, body with AI paths off", BAD,
                                                      '(brmh_p # 1) disableAI "PATH"; (brmh_p # 1) disableAI "MOVE"; true'),
    "bad spot, medic is not the leader": trial(harness, "Bad spot, medic not the leader", BAD,
                                               "group (brmh_p # 1) selectLeader (brmh_p # 1); true"),
}
print("\nmetres moved of 30:", results, flush=True)
harness.stop()
print("done", flush=True)
