"""Scene 3 of the demo, watched closely: what each try does."""
import time

from spike_ace_lib import game, run, show

from arma_harness.commander.operator import load_sqf

harness = game()
run(harness, load_sqf("commander_boot.sqf"))
run(harness, """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
private _house = nearestObject [[4150, 4130, 0], "Land_i_Stone_HouseBig_V2_F"];
private _spot = ((_house buildingPos -1) select {(_x # 2) < 1}) # 0;
private _group = createGroup [west, false];
brmh_m = _group createUnit ["B_medic_F", [4200, 4110, 0], [], 0, "CAN_COLLIDE"];
brmh_h = _group createUnit ["B_Soldier_F", [_spot # 0, _spot # 1, 0], [], 0, "CAN_COLLIDE"];
_group selectLeader brmh_m;
[brmh_h, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
time.sleep(5)
show("body", run(harness, "getPosATL brmh_h"))
show("spots", run(harness, "[brmh_h, getPosATL brmh_m] call brmh_cmd_fnc_nearBody"))
run(harness, "brmh_c = [brmh_m, brmh_h, [4200, 4090, 0]] call brmh_cmd_fnc_startCarry; true")
for i in range(40):
    time.sleep(3)
    row = run(harness, """
    [round (time - (brmh_c get "ordered")), brmh_c get "tries", brmh_c get "state", brmh_c get "result",
     round ((brmh_m distance brmh_h) * 10) / 10, round (brmh_m distance2D [4200, 4110]), round speed brmh_m,
     currentCommand brmh_m, unitReady brmh_m, (getPosATL brmh_m) # 2, expectedDestination brmh_m # 0]
    """)
    print(f"{(i + 1) * 3:3d}s", row, flush=True)
    if row[2] in ("carrying", "done"):
        break
harness.stop()
print("done", flush=True)
