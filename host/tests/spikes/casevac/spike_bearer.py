"""Can a man carrying someone fight? And is he a target? One carrying, and one the same on foot beside him, with enemies in view."""
import time

from spike_ace_lib import game, run, show

from arma_harness.commander.operator import load_sqf

harness = game()
run(harness, load_sqf("commander_boot.sqf"))
run(harness, """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
brmh_shots = createHashMap;
brmh_hits = createHashMap;
brmh_fnc_watch = {
    params ["_man", "_label"];
    _man setVariable ["brmh_label", _label];
    _man addEventHandler ["Fired", {
        params ["_man"];
        private _label = _man getVariable "brmh_label";
        brmh_shots set [_label, (brmh_shots getOrDefault [_label, 0]) + 1];
    }];
    _man addEventHandler ["Hit", {
        params ["_man"];
        private _label = _man getVariable "brmh_label";
        brmh_hits set [_label, (brmh_hits getOrDefault [_label, 0]) + 1];
    }];
};
brmh_fnc_trial = {
    params ["_x0"];
    private _group = createGroup [west, false];
    private _bearer = _group createUnit ["B_Soldier_F", [_x0, 1500, 0], [], 0, "CAN_COLLIDE"];
    private _hurt = _group createUnit ["B_Soldier_F", [_x0 + 3, 1500, 0], [], 0, "CAN_COLLIDE"];
    [_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
    private _free = (createGroup [west, false]) createUnit ["B_Soldier_F", [_x0 + 40, 1500, 0], [], 0, "CAN_COLLIDE"];
    _free setVariable ["brmh_cmd_x", 1];
    [_bearer, format ["carrier %1", _x0]] call brmh_fnc_watch;
    [_free, format ["free %1", _x0]] call brmh_fnc_watch;
    brmh_trials pushBack [_bearer, _free, _hurt];
    [_bearer, _hurt, [_x0 + 3, 1300, 0]] call brmh_cmd_fnc_startCarry;
    private _east = createGroup [east, false];
    for "_i" from 0 to 3 do {
        private _man = _east createUnit ["O_Soldier_F", [_x0 + _i * 8, 1600, 0], [], 0, "CAN_COLLIDE"];
        _man disableAI "PATH";
        _man reveal [_bearer, 4];
        _man reveal [_free, 4];
        _bearer reveal [_man, 4];
        _free reveal [_man, 4];
    };
    brmh_easts pushBack _east;
};
brmh_trials = [];
brmh_easts = [];
{[_x] call brmh_fnc_trial} forEach [1000, 1400, 1800];
true
""")
READ = """
brmh_trials apply {
    _x params ["_bearer", "_free", "_hurt"];
    [alive _bearer, lifeState _bearer, str attachedTo _hurt, alive _free, lifeState _free, alive _hurt,
     round (_bearer distance2D [getPosATL _bearer # 0, 1500])]
}
"""
print("  [carrier alive, state, body attached to, free alive, state, body alive, carried m]", flush=True)
time.sleep(14)
show("  lifted", run(harness, READ))
for _ in range(9):
    time.sleep(6)
    show("  shots, hits", run(harness, "[brmh_shots toArray false, brmh_hits toArray false]"))
show("  end", run(harness, READ))
harness.stop()
print("done", flush=True)
