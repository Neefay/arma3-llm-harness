/*
	NAME: brmh_cmd_fnc_spawnVehicle
	DESCRIPTION: Places a scenario's vehicle or gun, under its id, marked as the harness's own so the reset between
		battles deletes it. An aircraft can start flying, and gets ACE's guided bombs where ACE has them
		(brmh_cmd_fnc_aceBombs); a gun's fire is tracked. Operator action, never reachable by the commander.
	PARAMETERS:
		0 - Scenario id (STRING)
		1 - Class (STRING)
		2 - Position [x, y] (ARRAY)
		3 - (OPTIONAL) Rounds by kind for the main turret, [[word, rounds], ...] as brmh_cmd_fnc_setAmmo takes them,
		    empty to leave it as it comes (ARRAY) - Default: []
		4 - (OPTIONAL) Height to start flying at, metres; 0 on the ground (NUMBER) - Default: 0
		5 - (OPTIONAL) A magazine for each pylon in order, "" to leave one as it comes (ARRAY) - Default: []
	USAGE:
		["V1", "B_Mortar_01_F", [4150, 3350], [["HE", 16], ["SMOKE", 4]]] call brmh_cmd_fnc_spawnVehicle;
		["V2", "B_Heli_Attack_01_dynamicLoadout_F", [2500, 1500], [], 150] call brmh_cmd_fnc_spawnVehicle;
	RETURNS: Its display name (STRING)
	ENVIRONMENT: Server, unscheduled
*/
params [["_key", "", [""]], ["_class", "", [""]], ["_at", [], [[]], 2], ["_ammo", [], [[]]], ["_fly", 0, [0]], ["_pylons", [], [[]]]];
private _vehicle = createVehicle [_class, _at + [0], [], 0, ["NONE", "FLY"] select (_fly > 0)];
_vehicle setVariable ["brmh_cmd_spawned", true];
if (_fly > 0) then {
	// Airborne and already moving, so it doesn't stall in its first second.
	_vehicle setPosASL [_at # 0, _at # 1, (getTerrainHeightASL _at) + _fly];
	_vehicle setVelocityModelSpace [0, [40, 100] select (_vehicle isKindOf "Plane"), 0];
	_vehicle flyInHeight _fly;
	_vehicle setVariable ["brmh_cmd_flyHeight", _fly];
};
{
	if (_x isNotEqualTo "") then {
		[_vehicle, _forEachIndex + 1, _x] call brmh_cmd_fnc_setPylon;
	};
} forEach _pylons;
[_vehicle] call brmh_cmd_fnc_aceBombs;
_vehicle setVariable ["brmh_cmd_key", _key];
brmh_cmd_vehicles set [_key, _vehicle];
if (getNumber (configOf _vehicle >> "artilleryScanner") > 0) then {
	[_vehicle] call brmh_cmd_fnc_trackGun;
};
if (_ammo isNotEqualTo []) then {
	[_vehicle, _ammo] call brmh_cmd_fnc_setAmmo;
};
getText (configOf _vehicle >> "displayName")
