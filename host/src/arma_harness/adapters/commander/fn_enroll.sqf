/*
	NAME: brmh_cmd_fnc_enroll
	DESCRIPTION: Spawns one station's group and puts it on the command net. Operator action, never reachable by the commander.
	PARAMETERS:
		0 - Callsign (STRING)
		1 - Side (SIDE)
		2 - Number of soldiers (NUMBER)
		3 - Unit class (STRING)
		4 - Position [x, y] (ARRAY)
	USAGE:
		["Alpha", west, 4, "B_Soldier_F", [3050, 3050]] call brmh_cmd_fnc_enroll;
	RETURNS: Number of soldiers created
	ENVIRONMENT: Server
*/
params [["_callsign", "", [""]], ["_side", west, [west]], ["_count", 1, [0]], ["_class", "", [""]], ["_at", [], [[]], 2]];
private _group = createGroup [_side, false];
for "_i" from 1 to _count do {
	_group createUnit [_class, (_at + [0]) getPos [3 * _i, 90], [], 0, "NONE"];
};
_group setGroupIdGlobal [_callsign];
private _rounds = 0;
{
	_rounds = _rounds + ([_x] call brmh_cmd_fnc_rounds);
} forEach units _group;
_group setVariable ["brmh_cmd_baseline", count units _group];
_group setVariable ["brmh_cmd_roundsBaseline", _rounds];
brmh_cmd_stations set [_callsign, _group];
count units _group
