/*
	NAME: brmh_cmd_fnc_strikeOrder
	DESCRIPTION: Sends a station's aircraft to bomb a grid, then back to its hold. A new order calls off the one before.
		The run starts BRMH_CMD_RUN_IN_M out on the heading given. With none it's flown from where the aircraft is:
		straight at the grid when that's farther than the run-in point, by the run-in point when it's nearer. On the
		run the pilot fights nothing, and a plane goes up to at least 700 m. Refused, with the reason said, when it
		isn't flying, has no bombs, or has only bombs that need a laser on the target.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Grid centre [x, y] (ARRAY)
		3 - (OPTIONAL) Bombs to drop, 1 to 4 (NUMBER) - Default: 1
		4 - (OPTIONAL) Run-in heading in degrees, or -1 for straight from where the aircraft is (NUMBER) - Default: -1
	USAGE:
		[_group, "O-0004", [3750, 2450], 2, 0] call brmh_cmd_fnc_strikeOrder;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. Called by brmh_cmd_fnc_order for a "strike" order.
*/
params [["_group", grpNull, [grpNull]], ["_order", "", [""]], ["_aim", [], [[]], [2, 3]], ["_bombs", 1, [0]], ["_heading", -1, [0]]];
private _vehicle = vehicle leader _group;
{
	if ((_x get "GROUP") isEqualTo _group and {
		((_x get "SPEC") get "KIND") in ["sortie", "strike"]
	}) then {
		_x call ["#END", ["called off"]];
	};
} forEach brmh_cmd_builds;
if (not (_vehicle isKindOf "Air") or {
	not alive _vehicle
}) exitWith {
	[_group, _order, "strike", "", "not flying"] call brmh_cmd_fnc_careSay;
};
private _bomb = [_vehicle] call brmh_cmd_fnc_bombWeapon;
if (_bomb isEqualTo []) exitWith {
	[_group, _order, "strike", "", "no bombs"] call brmh_cmd_fnc_careSay;
};
if ((_bomb # 0) isEqualTo "") exitWith {
	[_group, _order, "strike", "", "laser only"] call brmh_cmd_fnc_careSay;
};
_bomb params ["_weapon", "_guidance", "_side"];
[_vehicle] call brmh_cmd_fnc_countShots;
private _given = _heading >= 0;
if (not _given) then {
	_heading = _vehicle getDir _aim;
};
private _ip = _aim getPos [BRMH_CMD_RUN_IN_M, _heading + 180];
private _direct = not _given and {
	(_vehicle distance2D _aim) > BRMH_CMD_RUN_IN_M - 1000
};
[_group] call brmh_cmd_fnc_clearRoute;
(_group addWaypoint [[_ip, (_aim select [0, 2]) + [0]] select _direct, 0]) setWaypointType "MOVE";
// On the run he flies it, and nothing else: no turning off to fight on the way.
_group setBehaviour "CARELESS";
_group setCombatMode "BLUE";
if (_vehicle isKindOf "Plane") then {
	_vehicle flyInHeight ((_vehicle getVariable ["brmh_cmd_flyHeight", 300]) max 700);
};
brmh_cmd_builds pushBack ([brmh_cmd_strikeMachine, [["GROUP", _group], ["ORDER", _order], ["SUBJECT", _vehicle getVariable ["brmh_cmd_key", ""]], ["VEHICLE", _vehicle], ["AIM", AGLToASL ((_aim select [0, 2]) + [0])], ["BOMBS", _bombs], ["HEADING", _heading], ["IP", _ip], ["DIRECT", _direct], ["WEAPON", _weapon], ["GUIDANCE", _guidance], ["SIDE", _side], ["GRID", [mapGridPosition _aim] call brmh_cmd_fnc_spokenGrid], ["PASSES", 0], ["BOMBS_BEFORE", _vehicle getVariable ["brmh_cmd_bombs", 0]], ["NEXT", 0]]] call brmh_cmd_fnc_newMachine);
