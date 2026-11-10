"""Does a man who's already carrying someone shoot? The enemy appears only once he's lifted, and doesn't shoot back, so nothing
else stops him. A free man the same distance off is the control."""
import time

from spike_ace_lib import game, run, show

from arma_harness.commander.operator import load_sqf

harness = game()
run(harness, load_sqf("commander_boot.sqf"))
run(harness, """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
brmh_shots = createHashMap;
brmh_fnc_watch = {
    params ["_man", "_label"];
    _man setVariable ["brmh_label", _label];
    _man addEventHandler ["Fired", {
        params ["_man"];
        private _label = _man getVariable "brmh_label";
        brmh_shots set [_label, (brmh_shots getOrDefault [_label, 0]) + 1];
    }];
};
brmh_fnc_trial = {
    params ["_x0"];
    private _group = createGroup [west, false];
    private _bearer = _group createUnit ["B_Soldier_F", [_x0, 1500, 0], [], 0, "CAN_COLLIDE"];
    private _hurt = _group createUnit ["B_Soldier_F", [_x0 + 3, 1500, 0], [], 0, "CAN_COLLIDE"];
    [_hurt, true, 0, false] call ace_medical_fnc_setUnconscious;
    private _free = (createGroup [west, false]) createUnit ["B_Soldier_F", [_x0 + 40, 1400, 0], [], 0, "CAN_COLLIDE"];
    [_bearer, format ["carrier %1", _x0]] call brmh_fnc_watch;
    [_free, format ["free %1", _x0]] call brmh_fnc_watch;
    brmh_trials pushBack [_bearer, _free, _hurt];
    [_bearer, _hurt, [_x0 + 3, 1000, 0]] call brmh_cmd_fnc_startCarry;
};
brmh_trials = [];
{[_x] call brmh_fnc_trial} forEach [1000, 1400, 1800];
true
""")
READ = """
brmh_trials apply {
    _x params ["_bearer", "_free", "_hurt"];
    [lifeState _bearer, str attachedTo _hurt, currentWeapon _bearer, animationState _bearer, lifeState _free,
     round (_bearer distance2D [getPosATL _bearer # 0, 1500])]
}
"""
print("  [carrier state, body attached to, carrier's weapon, animation, free state, carried m]", flush=True)
time.sleep(25)
show("  lifted", run(harness, READ))
run(harness, """
{
    _x params ["_bearer", "_free"];
    private _east = createGroup [east, false];
    private _at = getPosATL _bearer;
    for "_i" from 0 to 3 do {
        private _man = _east createUnit ["O_Soldier_F", [(_at # 0) + _i * 8, (_at # 1) - 120, 0], [], 0, "CAN_COLLIDE"];
        _man allowDamage false;
        _man disableAI "PATH";
        _man setCombatMode "BLUE";
        _bearer reveal [_man, 4];
        _free reveal [_man, 4];
    };
} forEach brmh_trials;
true
""")
for _ in range(7):
    time.sleep(6)
    show("  shots", run(harness, "brmh_shots toArray false"))
show("  end", run(harness, READ))
harness.stop()
print("done", flush=True)
