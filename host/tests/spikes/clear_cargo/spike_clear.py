"""Why did two squads report Camp Maxwell's B4 "checked, nothing seen" with a man standing inside it?

A soldier is sent to the house's position the way CLEAR sends him, and watched for a minute: how close he gets, and
what noticeNearby would make of the man there. Stratis, Military Cargo House (Rusty) at [3318, 2940].
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

from arma_harness.commander.operator import load_sqf  # noqa: E402

harness, run = in_fresh_game("commander_stratis")
run(load_sqf("commander_boot.sqf"))
print("house", run("""
private _h = (nearestObjects [[3318, 2940], ["House"], 6]) # 0;
spike_house = _h;
[typeOf _h, getPosATL _h apply {round _x}, (_h buildingPos -1) apply {_x apply {round (_x * 10) / 10}},
 getPosATL _h select 2, getTerrainHeightASL getPosATL _h]
"""))
for start in ([3270, 2945], [3330, 2900]):
    print("from", start, run(f"""
    {{ deleteVehicle _x }} forEach (missionNamespace getVariable ["spike_men", []]);
    private _spot = (spike_house buildingPos -1) # 0;
    private _e = (createGroup [east, true]) createUnit ["O_Soldier_F", [0, 0, 0], [], 0, "CAN_COLLIDE"];
    _e setPosATL _spot; _e disableAI "PATH";
    private _w = (createGroup [west, true]) createUnit ["B_Soldier_F", {start} + [0], [], 0, "NONE"];
    spike_men = [_e, _w]; spike_spot = _spot;
    _w doMove _spot;
    [getPosATL _e apply {{round (_x * 10) / 10}}]
    """))
    for _ in range(12):
        time.sleep(5)
        print("   ", run("""
        spike_men params ["_e", "_w"];
        [round ((_w distance spike_spot) * 10) / 10, round ((_w distance _e) * 10) / 10, unitReady _w,
         round (([_w, "VIEW", _e] checkVisibility [eyePos _w, eyePos _e]) * 100) / 100,
         round ((_w knowsAbout _e) * 10) / 10, alive _e, alive _w, currentCommand _w,
         (getPosATL _w) apply {round (_x * 10) / 10}]
        """), flush=True)
print(harness.stop() if "--stop" in sys.argv else "game left up")
