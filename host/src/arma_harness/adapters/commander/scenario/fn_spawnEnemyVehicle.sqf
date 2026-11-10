/*
	NAME: brmh_cmd_fnc_spawnEnemyVehicle
	DESCRIPTION: An enemy weapon or vehicle with its own crew, for a scenario: an HMG on a tripod facing an approach, an
		armed car, a tank. Operator action. Its crew is an enemy group like any other, so clearing the enemy means them
		too. The vehicle is the harness's own, so the reset between battles deletes it.
	PARAMETERS:
		0 - Group id (STRING)
		1 - Side (SIDE)
		2 - Vehicle class (STRING)
		3 - Position [x, y] (ARRAY)
		4 - (OPTIONAL) Facing, degrees (NUMBER) - Default: 0
		5 - (OPTIONAL) Mode: "hold" stays put, "patrol" drives around the area (STRING) - Default: "hold"
		6 - (OPTIONAL) Radius in metres, for a patrol (NUMBER) - Default: 100
	USAGE:
		["East Gun", east, "O_HMG_01_high_F", [3700, 2400], 210, "hold", 0] call brmh_cmd_fnc_spawnEnemyVehicle;
	RETURNS: How many crew it has (NUMBER)
	ENVIRONMENT: Server, unscheduled
*/
params [["_id", "", [""]], ["_side", east, [east]], ["_class", "", [""]], ["_at", [], [[]], 2], ["_dir", 0, [0]], ["_mode", "hold", [""]], ["_radius", 100, [0]]];
if (not isClass (configFile >> "CfgVehicles" >> _class)) exitWith {
	["Spawn", "ERROR", "%1: no such vehicle class %2", [_id, _class]] call brmh_cmd_fnc_log;
	0
};
// A gun on a tripod goes on level ground near the place: on Stratis one on a slope tipped over within seconds and threw
// off its gunner. Vehicles sit on slopes well enough, and stay where they're put.
private _tries = [[0, 0]];
{
	private _distance = _x;
	{
		_tries pushBack [_distance, _x];
	} forEach [0, 45, 90, 135, 180, 225, 270, 315];
} forEach [5, 10, 20, 30, 40];
private _spot = _at + [0];
if (_class isKindOf "StaticWeapon") then {
	{
		private _try = (_at + [0]) getPos _x;
		if ((_try isFlatEmpty [-1, -1, 0.15, 5, 0, false, objNull]) isNotEqualTo []) exitWith {
			_spot = _try;
		};
	} forEach _tries;
};
private _vehicle = createVehicle [_class, _spot, [], 0, ["NONE", "CAN_COLLIDE"] select (_class isKindOf "StaticWeapon")];
_vehicle setDir _dir;
if (_class isKindOf "StaticWeapon") then {
	_vehicle setVectorUp (surfaceNormal _spot);
};
_vehicle setVariable ["brmh_cmd_spawned", true];
private _group = createVehicleCrew _vehicle;
if (side _group isNotEqualTo _side) then {
	private _made = _group;
	_group = createGroup [_side, false];
	(crew _vehicle) joinSilent _group;
	deleteGroup _made;
};
_group setGroupIdGlobal [_id];
brmh_cmd_enemies pushBack _group;
// It's what a squad will see first, so it gets its key now: the list follows it whoever reports it.
[_vehicle] call brmh_cmd_fnc_targetKey;
if (_mode isEqualTo "hold") then {
	{
		_x disableAI "PATH";
	} forEach crew _vehicle;
};
if (_mode isEqualTo "patrol") then {
	[_group, _at + [0], _radius] call BIS_fnc_taskPatrol;
};
count crew _vehicle
