/*
	NAME: brmh_cmd_fnc_spawnEnemy
	DESCRIPTION: Spawns an opposing group for a scenario. Operator action. Enemies are never on the net.
	PARAMETERS:
		0 - Group id (STRING)
		1 - Side (SIDE)
		2 - Number of soldiers (NUMBER)
		3 - Unit class (STRING)
		4 - Position [x, y] (ARRAY)
		5 - Mode: "hold" stays put, "garrison" takes positions in nearby buildings, "patrol" walks the area (STRING)
		6 - Radius in metres (NUMBER)
		7 - (OPTIONAL) For a garrison, the positions it may take, from brmh_cmd_fnc_probePositions (ARRAY) - Default: any
	USAGE:
		["East 1", east, 6, "O_Soldier_F", [4100, 4160], "garrison", 120] call brmh_cmd_fnc_spawnEnemy;
	RETURNS: Number of soldiers created
	ENVIRONMENT: Server
*/
params [["_id", "", [""]], ["_side", east, [east]], ["_count", 1, [0]], ["_class", "", [""]], ["_at", [], [[]], 2], ["_mode", "hold", [""]], ["_radius", 100, [0]], ["_reachable", [], [[]]]];
private _centre = _at + [0];
private _group = createGroup [_side, false];
for "_i" from 1 to _count do {
	_group createUnit [_class, _centre getPos [3 * _i, 90], [], 0, "NONE"];
};
_group setGroupIdGlobal [_id];
brmh_cmd_enemies pushBack _group;
if (_mode isEqualTo "garrison") then {
	// Only where a soldier was seen to get, when the operator probed first: see brmh_cmd_fnc_probePositions.
	private _spots = +_reachable;
	if (_spots isEqualTo []) then {
		{
			_spots append ([_x] call brmh_cmd_fnc_safePositions);
		} forEach nearestObjects [_centre, ["House"], _radius];
	};
	{
		if (_spots isNotEqualTo []) then {
			_x setPosATL (_spots deleteAt floor random count _spots);
			_x disableAI "PATH";
		};
	} forEach units _group;
};
if (_mode isEqualTo "patrol") then {
	[_group, _centre, _radius] call BIS_fnc_taskPatrol;
};
count units _group
