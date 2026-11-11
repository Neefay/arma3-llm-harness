/*
	NAME: spawn_vehicle
	DESCRIPTION: Spawn an empty vehicle next to someone, on clear ground, facing the way they face. Aircraft can
		start flying. Classes: B_MRAP_01_hmg_F (Hunter HMG), B_APC_Wheeled_01_cannon_F (Badger IFV),
		B_MBT_01_cannon_F (tank), B_Heli_Transport_01_F (Ghost Hawk), C_Offroad_01_F (civilian pickup); find others
		with find_class.
	PARAMETERS:
		0 - class (STRING): the vehicle's class
		1 - near (OBJECT, default "player"): who it appears next to
		2 - distance (NUMBER, default 15): how far away, in m
		3 - flying (BOOL, default false): start an aircraft in the air
	RETURNS: [handle, display name, distance in m] (ARRAY)
	TARGET: server
	TAGS: spawn, vehicle, car, tank, helicopter, aircraft, create
	EXAMPLE: {"class": "C_Offroad_01_F"}
*/
params ["_class", "_near", "_distance", "_flying"];
if (not isClass (configFile >> "CfgVehicles" >> _class)) exitWith {
	format ["ERROR: there's no vehicle class %1: find one with find_class", _class]
};
if (isNull _near) exitWith {
	"ERROR: no such unit to spawn it near"
};
private _around = _near getPos [_distance, getDir _near + 40];
private _at = _around findEmptyPosition [0, 50, _class];
if (_at isEqualTo []) then {
	_at = _around;
};
private _vehicle = createVehicle [_class, _at, [], 0, ["NONE", "FLY"] select _flying];
_vehicle setDir getDir _near;
private _handle = [[_vehicle], typeOf _vehicle] call brmh_lib_fnc_keep;
[_handle, getText (configOf _vehicle >> "displayName"), round (_near distance _vehicle)]
