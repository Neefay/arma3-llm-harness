"""How does a squad's idea of what it's looking at change over time? An enemy HMG on a tripod, a light armed vehicle and
a tank, each with its own crew, in front of a watching squad on Stratis. Every few seconds: the type the squad's leader
believes each one is (nearTargets), how sure he is (knowsAbout), and what that type is in the class tree.

    spike_kinds.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

harness, run = in_fresh_game("commander_stratis")
WATCH = [3450, 2650]  # hilltop 148, open ground east of Agios Ioannis
print("placed", run(f"""
{{ deleteVehicle _x }} forEach (missionNamespace getVariable ["spike_things", []]);
spike_things = [];
private _w = createGroup [west, true];
for "_i" from 1 to 4 do {{ _w createUnit ["B_Soldier_F", {WATCH} getPos [3 * _i, 90], [], 0, "NONE"] }};
spike_things append units _w; spike_watcher = leader _w;
spike_watcher setDir 220;
spike_targets = [];
{{
    _x params ["_class", "_distance"];
    private _spot = [];
    for "_b" from 0 to 355 step 5 do {{
        private _p = {WATCH} getPos [_distance, _b];
        if (_spot isEqualTo [] and {{ not surfaceIsWater _p }} and {{
            ([spike_watcher, "VIEW"] checkVisibility [eyePos spike_watcher, (AGLToASL _p) vectorAdd [0, 0, 1.5]]) > 0.8
        }}) then {{ _spot = _p }};
    }};
    private _v = createVehicle [_class, _spot, [], 0, "CAN_COLLIDE"];
    _v setDir (_v getDir spike_watcher);
    createVehicleCrew _v;
    spike_targets pushBack _v; spike_things pushBack _v; spike_things append crew _v;
}} forEach [["O_HMG_01_high_F", 250], ["O_MRAP_02_hmg_F", 400], ["O_MBT_02_cannon_F", 550]];
spike_targets apply {{ typeOf _x }}
"""))
for _ in range(16):
    time.sleep(5)
    print(round(float(run("time"))), run("""
    private _near = spike_watcher nearTargets 2000;
    spike_targets apply {
        private _object = _x;
        private _entry = _near findIf { (_x # 4) isEqualTo _object };
        private _type = if (_entry < 0) then { "" } else { (_near # _entry) # 1 };
        [typeOf _object, count crew _object, _type, getNumber (configFile >> "CfgVehicles" >> _type >> "scope"),
         round ((spike_watcher knowsAbout _object) * 100) / 100,
         if (_type isEqualTo "") then { [] } else {
             ([configFile >> "CfgVehicles" >> _type, true] call BIS_fnc_returnParents) select [0, 4] }]
    }
    """), flush=True)
print(harness.stop() if "--stop" in sys.argv else "game left up")
