"""Spike 4: what shells do to people, who gets blamed, buildings, smoke, sight of impacts, several guns, vehicles, and impossible shots."""
from __future__ import annotations

import time

from spike_arty_lib import TRACK, game, run, show

h = game()
run(h, TRACK)
run(h, """
brmh_spike_fnc_listen = {
	params ["_man", "_log"];
	_man setVariable ["brmh_log", _log];
	{
		private _kind = _x;
		_man addEventHandler [_kind, compile format ['
			params ["_u", "_a", "_b", "_c"];
			(_u getVariable "brmh_log") pushBack ["%1", time];
		', _kind]];
	} forEach ["Suppressed", "Explosion", "FiredNear", "Hit", "Dammaged"];
	_man addEventHandler ["Killed", {
		params ["_u", "_killer", "_instigator"];
		(_u getVariable "brmh_log") pushBack ["Killed", time, typeOf _killer, name _killer, side group _instigator, typeOf _instigator, isNull _instigator];
	}];
};
brmh_spike_fnc_men = {
	params ["_at", "_side", "_count"];
	private _group = createGroup [_side, false];
	for "_i" from 1 to _count do {
		private _man = _group createUnit [["B_Soldier_F", "O_Soldier_F"] select (_side isEqualTo east), _at, [], 2, "NONE"];
		[_man, []] call brmh_spike_fnc_listen;
	};
	_group
};
brmh_spike_fnc_tally = {
	params ["_group", "_at"];
	private _events = createHashMap;
	private _killed = [];
	{
		{
			if (_x # 0 isEqualTo "Killed") then { _killed pushBack (_x select [2]); } else { _events set [_x # 0, (_events getOrDefault [_x # 0, 0]) + 1]; };
		} forEach (_x getVariable ["brmh_log", []]);
	} forEach (units _group);
	[{alive _x} count units _group, count units _group, _events toArray false, _killed, behaviour leader _group, (units _group) apply {round (_x distance2D _at)}, (units _group) apply {getSuppression _x}]
};
true
""")

NOTICE = """
params ["_name", "_at", "_sideName"];
private _side = [east, west] select (_sideName isEqualTo "west");
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
private _man = gunner _gun;
private _gunner0 = [rating _man, side group _man, name _man];
private _target = _gun getPos [800, 90];
private _rows = [];
{
	private _spot = _target getPos [_x, 0];
	_rows pushBack [_x, [_spot, _side, 2] call brmh_spike_fnc_men, _spot];
} forEach [8, 25, 50, 100, 200, 400];
sleep 3;
private _before = _rows apply {behaviour leader (_x # 1)};
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 8];
sleep 55;
private _knows = _rows apply {
	private _g = _x # 1;
	private _alive = (units _g) select {alive _x};
	if (_alive isEqualTo []) then {-1} else {(_alive # 0) knowsAbout _man}
};
missionNamespace setVariable ["brmh_spike_" + _name, [_gunner0, [rating _man, side group _man, alive _man, side _man], _before, _rows apply {[_x # 0, [_x # 1, _x # 2] call brmh_spike_fnc_tally]}, _knows]];
"""
HOUSE = """
params ["_name", "_at", "_class"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
private _spot = _gun getPos [800, 90];
private _house = createVehicle [_class, _spot, [], 0, "CAN_COLLIDE"];
private _group = createGroup [east, false];
private _inside = (_house buildingPos -1) select [0, 3];
{
	private _soldier = _group createUnit ["O_Soldier_F", [0, 0, 0], [], 0, "CAN_COLLIDE"];
	_soldier setPosATL _x;
	_soldier disableAI "PATH";
	[_soldier, []] call brmh_spike_fnc_listen;
} forEach _inside;
private _outside = [_spot getPos [25, 180] , east, 2] call brmh_spike_fnc_men;
{ _x disableAI "PATH"; } forEach units _outside;
sleep 3;
private _heights = (units _group) apply {getPosATL _x # 2};
private _start = [count (_house buildingPos -1), damage _house];
_gun doArtilleryFire [_spot, "8Rnd_82mm_Mo_shells", 8];
sleep 14;
_gun doArtilleryFire [_spot, "8Rnd_82mm_Mo_shells", 8];
sleep 50;
private _after = nearestObjects [_spot, ["House"], 15];
missionNamespace setVariable ["brmh_spike_" + _name, [_class, _start, _heights, [alive _house, damage _house, count (_house buildingPos -1), isNull _house], _after apply {[typeOf _x, count (_x buildingPos -1), damage _x]}, [_group, _spot] call brmh_spike_fnc_tally, [_outside, _spot] call brmh_spike_fnc_tally, count (_gun getVariable "brmh_shells")]];
"""
SMOKE = """
params ["_name", "_at"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
private _centre = _gun getPos [800, 90];
private _a = createGroup [west, false] createUnit ["B_Soldier_F", _centre getPos [60, 180], [], 0, "NONE"];
private _b = createGroup [east, false] createUnit ["O_Soldier_F", _centre getPos [60, 0], [], 0, "NONE"];
{ _x disableAI "PATH"; _x setCombatMode "BLUE"; _x disableAI "AUTOTARGET"; _x disableAI "TARGET"; _x doWatch objNull; } forEach [_a, _b];
_a setDir 0; _b setDir 180;
sleep 2;
private _start = time;
private _see = {
	[round (time - _start), [_a, "VIEW", _b] checkVisibility [eyePos _a, eyePos _b], [_a, "FIRE", _b] checkVisibility [eyePos _a, eyePos _b], _a knowsAbout _b]
};
private _rows = [call _see];
_gun doArtilleryFire [_centre, "8Rnd_82mm_Mo_Smoke_white", 3];
for "_i" from 1 to 36 do {
	sleep 5;
	_rows pushBack (call _see);
};
missionNamespace setVariable ["brmh_spike_" + _name, _rows];
"""
SIGHT = """
params ["_name", "_at"];
private _gun = ["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
private _centre = _gun getPos [800, 90];
private _wall = createVehicle ["Land_i_House_Big_02_V1_F", _centre getPos [40, 180], [], 0, "CAN_COLLIDE"];
private _behind = createGroup [west, false] createUnit ["B_Soldier_F", _centre getPos [65, 180], [], 0, "CAN_COLLIDE"];
private _open = createGroup [west, false] createUnit ["B_Soldier_F", _centre getPos [65, 90], [], 0, "CAN_COLLIDE"];
private _far = createGroup [west, false] createUnit ["B_Soldier_F", _centre getPos [1400, 90], [], 0, "CAN_COLLIDE"];
sleep 2;
private _ground = [_centre # 0, _centre # 1, getTerrainHeightASL _centre + 0.6];
private _check = [_behind, _open, _far] apply {
	[round (_x distance2D _centre), [_x, "VIEW"] checkVisibility [eyePos _x, _ground], [_x, "GEOM"] checkVisibility [eyePos _x, _ground], [_x, "VIEW"] checkVisibility [eyePos _x, _ground vectorAdd [0, 0, 8]]]
};
_gun doArtilleryFire [_centre, "8Rnd_82mm_Mo_shells", 1];
sleep 35;
private _explode = (_gun getVariable "brmh_shells") apply {_x getOrDefault ["pos", []]};
missionNamespace setVariable ["brmh_spike_" + _name, [_check, _explode, getTerrainHeightASL _centre]];
"""
TWO = """
params ["_name", "_at"];
private _group = createGroup [west, false];
private _guns = [];
private _men = [];
{
	private _gun = createVehicle ["B_Mortar_01_F", _at vectorAdd [_x, 0, 0], [], 0, "NONE"];
	private _man = _group createUnit ["B_Soldier_F", _at, [], 2, "NONE"];
	_man moveInGunner _gun;
	[_gun] call brmh_spike_fnc_track;
	_guns pushBack _gun;
	_men pushBack _man;
} forEach [0, 10];
private _extra = _group createUnit ["B_Soldier_F", _at, [], 4, "NONE"];
sleep 2;
private _target = (_guns # 0) getPos [800, 90];
private _start = time;
_group selectLeader _extra;
sleep 0.5;
(_guns # 0) doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 4];
(_guns # 1) doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 4];
sleep 4;
doStop (_guns # 0);
sleep 16;
missionNamespace setVariable ["brmh_spike_" + _name, _guns apply {[count (_x getVariable "brmh_shells"), unitReady _x, currentCommand gunner _x, (_x getVariable "brmh_shells") apply {round ((_x get "fired") - _start)}]}];
"""
RIDE = """
params ["_name", "_at"];
private _group = createGroup [west, false];
for "_i" from 1 to 4 do { _group createUnit ["B_Soldier_F", _at, [], 5, "NONE"]; };
private _car = createVehicle ["B_MRAP_01_hmg_F", _at vectorAdd [30, 0, 0], [], 0, "NONE"];
private _men = units _group;
private _lead = leader _group;
private _others = _men - [_lead];
sleep 1;
(_others # 0) assignAsDriver _car;
(_others # 1) assignAsGunner _car;
(_others # 2) assignAsCargoIndex [_car, 1];
_lead assignAsCargoIndex [_car, 0];
_group addVehicle _car;
_men orderGetIn true;
private _start = time;
waitUntil {sleep 0.5; ({vehicle _x isEqualTo _car} count _men) isEqualTo 4 or time > _start + 60};
private _in = [time - _start, fullCrew _car apply {[name (_x # 0) isEqualTo name _lead, _x # 1, _x # 2, _x # 3]}, _men apply {assignedVehicleRole _x}];
private _wp = _group addWaypoint [_at vectorAdd [30, 400, 0], 0];
_wp setWaypointType "MOVE";
_group setCurrentWaypoint _wp;
private _from = getPos _car;
sleep 25;
private _drove = [_car distance2D _from, speed _car, _car distance2D (_at vectorAdd [30, 400, 0])];
sleep 15;
_men orderGetIn false;
{ unassignVehicle _x; } forEach _men;
sleep 12;
missionNamespace setVariable ["brmh_spike_" + _name, [_in, _drove, {vehicle _x isEqualTo _car} count _men, (_men select {alive _x}) apply {typeOf vehicle _x}, currentCommand _lead]];
"""
EDGE = """
params ["_name", "_at", "_range", "_case"];
private _gun = if (_case isEqualTo "empty") then {
	private _g = createVehicle ["B_Mortar_01_F", _at + [0], [], 0, "NONE"];
	[_g] call brmh_spike_fnc_track;
	_g
} else {
	["B_Mortar_01_F", _at] call brmh_spike_fnc_gun;
};
sleep 2;
private _target = _gun getPos [_range, 90];
private _precheck = [_target inRangeOfArtillery [[_gun], "8Rnd_82mm_Mo_shells"], _gun getArtilleryETA [_target, "8Rnd_82mm_Mo_shells"]];
_gun doArtilleryFire [_target, "8Rnd_82mm_Mo_shells", 2];
sleep 15;
private _man = gunner _gun;
private _mid = [count (_gun getVariable "brmh_shells"), unitReady _gun, if (isNull _man) then {"nobody"} else {currentCommand _man}];
private _late = [];
if (_case isEqualTo "killed") then { _man setDamage 1; };
_gun doArtilleryFire [_gun getPos [800, 90], "8Rnd_82mm_Mo_shells", 2];
sleep 10;
_late = [count (_gun getVariable "brmh_shells"), unitReady _gun];
missionNamespace setVariable ["brmh_spike_" + _name, [_case, _range, _precheck, _mid, _late]];
"""
names = []


def launch(name: str, code: str, *args) -> None:
    names.append(name)
    run(h, f"brmh_spike_{name} = nil; _this spawn {{{code}}}; true", [name, *args])


launch("notice_west", NOTICE, [500, 500], "west")
launch("notice_east", NOTICE, [500, 1600], "east")
launch("house_small", HOUSE, [500, 2700], "Land_i_House_Small_02_V1_F")
launch("house_big", HOUSE, [500, 3500], "Land_i_House_Big_02_V1_F")
launch("smoke", SMOKE, [500, 4300])
launch("sight", SIGHT, [500, 5100])
launch("two", TWO, [500, 6000])
launch("ride", RIDE, [2500, 500])
for index, (rng, case) in enumerate(((6000, "far"), (10, "close"), (800, "empty"), (800, "killed"))):
    launch(f"edge_{case}", EDGE, [2500, 2000 + 500 * index], rng, case)

deadline = time.time() + 260
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
