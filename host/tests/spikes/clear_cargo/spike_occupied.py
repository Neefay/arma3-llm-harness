"""A clearer sent to a one-position building whose only position an enemy is standing on (Camp Maxwell B5, the cargo
house AI can get into). What can he see of the man, eye to eye and eye to body, and does he fight?

    spike_occupied.py 3310 2951
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

from arma_harness.commander.operator import load_sqf  # noqa: E402

x, y = (float(v) for v in sys.argv[1:3]) if len(sys.argv) > 2 else (3310, 2951)
react = "--react" in sys.argv  # the defender may move once his enemy is close
harness, run = in_fresh_game("commander_stratis")
run(load_sqf("commander_boot.sqf"))
print("house", run(f"""
spike_house = (nearestObjects [[{x}, {y}], ["House"], 6] select {{ count (_x buildingPos -1) > 0 }}) # 0;
[typeOf spike_house, (spike_house buildingPos -1) apply {{ _x apply {{ round (_x * 10) / 10 }} }}]
"""))
print("placed", run("""
{ deleteVehicle _x } forEach (missionNamespace getVariable ["spike_men", []]);
private _spot = (spike_house buildingPos -1) # 0;
private _e = (createGroup [east, true]) createUnit ["O_Soldier_F", [0, 0, 0], [], 0, "CAN_COLLIDE"];
_e setPosATL _spot; _e disableAI "PATH";
private _w = (createGroup [west, true]) createUnit ["B_Soldier_F", spike_house getPos [30, 200], [], 0, "NONE"];
spike_men = [_e, _w]; spike_spot = _spot;
_w doMove _spot;
true
"""))
for _ in range(14):
    time.sleep(4)
    if react:
        run('spike_men params ["_e", "_w"]; if ((_e distance _w) < 15) then { _e enableAI "PATH" }; true')
    print("   ", run("""
    spike_men params ["_e", "_w"];
    private _eyes = [_w, "VIEW", _e] checkVisibility [eyePos _w, eyePos _e];
    private _body = [_w, "VIEW", _e] checkVisibility [eyePos _w,
        AGLToASL (_e modelToWorldVisual (_e selectionPosition "spine3"))];
    private _aim = [_w, "VIEW", _e] checkVisibility [eyePos _w, aimPos _e];
    [round ((_w distance _e) * 10) / 10, round (_eyes * 100) / 100, round (_body * 100) / 100, round (_aim * 100) / 100,
     round ((_w knowsAbout _e) * 10) / 10, alive _e, alive _w, currentCommand _w, unitReady _w]
    """), flush=True)
print(harness.stop() if "--stop" in sys.argv else "game left up")
