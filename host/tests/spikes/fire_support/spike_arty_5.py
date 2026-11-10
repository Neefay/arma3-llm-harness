"""Spike 5: noticing an abandoned gun, what a destroyed building leaves behind for CLEAR, and a crew under real assault."""
from __future__ import annotations

import time

from spike_arty_lib import TRACK, game, run, show

h = game()
run(h, TRACK)

SEE = """
params ["_name", "_at"];
private _man = createGroup [west, false] createUnit ["B_Soldier_F", _at, [], 0, "CAN_COLLIDE"];
_man setDir 90;
_man disableAI "PATH";
private _rows = [];
{
	_x params ["_label", "_class", "_range", "_blocked"];
	private _spot = _man getPos [_range, 90 * _forEachIndex];
	private _gun = createVehicle [_class, _spot, [], 0, "CAN_COLLIDE"];
	if (_blocked) then {
		createVehicle ["Land_i_House_Big_02_V1_F", _man getPos [_range * 0.5, 90 * _forEachIndex], [], 0, "CAN_COLLIDE"];
	};
	_rows pushBack [_label, _gun];
} forEach [["near open", "B_Mortar_01_F", 80, false], ["far open", "B_Mortar_01_F", 400, false], ["near behind house", "B_Mortar_01_F", 80, true], ["car far", "C_Offroad_01_F", 600, false]];
sleep 10;
private _found = _man nearEntities [["StaticWeapon", "LandVehicle"], 700];
private _out = _rows apply {
	_x params ["_label", "_gun"];
	private _eye = eyePos _man;
	private _centre = (getPosASL _gun) vectorAdd [0, 0, 1];
	[_label, round (_man distance2D _gun), _gun in _found, _man knowsAbout _gun, [_man, "VIEW", _gun] checkVisibility [_eye, _centre], side _gun, count crew _gun, canFire _gun, canMove _gun, someAmmo _gun]
};
private _targets = (_man targets [true, 700]) apply {typeOf _x};
missionNamespace setVariable ["brmh_spike_" + _name, [_out, _targets, count (_man nearTargets 700)]];
"""
RUIN = """
params ["_name", "_at", "_class"];
private _house = createVehicle [_class, _at, [], 0, "CAN_COLLIDE"];
sleep 1;
private _before = [typeOf nearestObject [_at, "House"], count (nearestObject [_at, "House"] buildingPos -1)];
_house setDamage 1;
sleep 8;
private _left = nearestObject [_at, "House"];
private _ruins = nearestObjects [_at, ["Ruins", "House", "Building"], 20];
private _group = createGroup [west, false];
for "_i" from 1 to 3 do {_group createUnit ["B_Soldier_F", _at vectorAdd [40, 0, 0], [], 3, "NONE"];};
private _spots = if (isNull _left or {_left distance2D _at > 15}) then {[]} else {_left buildingPos -1};
private _rows = [];
{
	private _man = (units _group) # (_forEachIndex min 2);
	_man doMove _x;
} forEach (_spots select [0, 3]);
sleep 30;
_rows = (units _group) apply {round (_x distance2D _at)};
private _reach = _spots select [0, 3] apply {
	private _spot = _x;
	selectMin ((units _group) apply {round (_x distance _spot)})
};
missionNamespace setVariable ["brmh_spike_" + _name, [_class, _before, [alive _house, isNull _house, typeOf _house, damage _house], [typeOf _left, _left distance2D _at, count (_left buildingPos -1), alive _left], _ruins apply {typeOf _x}, count _spots, _rows, _reach]];
"""
ASSAULT = """
params ["_name", "_at"];
private _group = createGroup [west, false];
for "_i" from 1 to 4 do {_group createUnit ["B_Soldier_F", _at, [], 4, "NONE"];};
private _gun = createVehicle ["B_Mortar_01_F", _at vectorAdd [6, 0, 0], [], 0, "NONE"];
private _man = (units _group) # 2;
_man moveInGunner _gun;
_man assignAsGunner _gun;
[_gun] call brmh_spike_fnc_track;
private _bad = createGroup [east, false];
for "_i" from 1 to 6 do {_bad createUnit ["O_Soldier_F", _at vectorAdd [0, 300, 0], [], 8, "NONE"];};
private _wp = _bad addWaypoint [_at, 0];
_wp setWaypointType "SAD";
_bad setCombatMode "RED";
private _rows = [];
private _start = time;
for "_i" from 1 to 18 do {
	sleep 5;
	_rows pushBack [round (time - _start), {alive _x} count units _group, {alive _x} count units _bad, alive _man, typeOf vehicle _man, alive gunner _gun, count (_gun getVariable "brmh_shells"), round (selectMin ((units _bad select {alive _x}) apply {_x distance2D _gun}) )];
};
_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2];
sleep 8;
missionNamespace setVariable ["brmh_spike_" + _name, [_rows select {true}, count (_gun getVariable "brmh_shells"), behaviour _man, canFire _gun, damage _gun]];
"""
names = []


def launch(name: str, code: str, *args) -> None:
    names.append(name)
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{code}}}; true", [name, *args])


launch("see", SEE, [2000, 7000, 0])
launch("ruin_small", RUIN, [3500, 7000, 0], "Land_i_House_Small_02_V1_F")
launch("ruin_big", RUIN, [3700, 7000, 0], "Land_i_House_Big_02_V1_F")
launch("ruin_shop", RUIN, [3900, 7000, 0], "Land_u_Shop_02_V1_F")
launch("ruin_tower", RUIN, [4300, 7000, 0], "Land_Cargo_Tower_V1_F")
launch("assault", ASSAULT, [5500, 7000, 0])

deadline = time.time() + 150
out = {}
while time.time() < deadline and len(out) < len(names):
    for name in names:
        if name not in out:
            value = run(h, f'if (isNil "brmh_spike_{name}") then {{""}} else {{brmh_spike_{name}}}')
            if value:
                out[name] = value
    time.sleep(5)
for name in names:
    show(name, out.get(name, "NOT FINISHED"))
print("errors", str(run(h, "true")))
h.stop()
print("stopped", flush=True)
