/*
	NAME: brmh_cmd_fnc_casOrder
	DESCRIPTION: Sends a station's aircraft to attack what it finds around a grid, then back to its hold. A new order
		calls off the one before.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Order id (STRING)
		2 - Grid centre [x, y] (ARRAY)
		3 - Radius, metres (NUMBER)
	ENVIRONMENT: Server
*/
params [["_group", grpNull, [grpNull]], ["_order", "", [""]], ["_aim", [], [[]], [2, 3]], ["_radius", 150, [0]]];
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
	[_group, _order, "sortie", "", "not flying"] call brmh_cmd_fnc_careSay;
};
[_vehicle] call brmh_cmd_fnc_countShots;
[_group] call brmh_cmd_fnc_clearRoute;
private _wp = _group addWaypoint [(_aim select [0, 2]) + [0], 0];
_wp setWaypointType "SAD";
_wp setWaypointCompletionRadius _radius;
_group setBehaviour "COMBAT";
_group setCombatMode "RED";
brmh_cmd_builds pushBack ([brmh_cmd_sortieMachine, [["GROUP", _group], ["ORDER", _order], ["SUBJECT", _vehicle getVariable ["brmh_cmd_key", ""]], ["VEHICLE", _vehicle], ["AIM", _aim], ["RADIUS", _radius], ["GRID", [mapGridPosition _aim] call brmh_cmd_fnc_spokenGrid], ["WAYPOINT", _wp # 1], ["SHOTS", _vehicle getVariable ["brmh_cmd_shots", 0]]]] call brmh_cmd_fnc_newMachine);
