/*
	NAME: brmh_cmd_fnc_holdAir
	DESCRIPTION: An aircraft circles a place until it's needed.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Position (ARRAY)
	ENVIRONMENT: Server
*/
params [["_group", grpNull, [grpNull]], ["_at", [], [[]], [2, 3]]];
_group setVariable ["brmh_cmd_hold", _at];
[_group] call brmh_cmd_fnc_clearRoute;
private _wp = _group addWaypoint [(_at select [0, 2]) + [0], 0];
_wp setWaypointType "LOITER";
_wp setWaypointLoiterType "CIRCLE_L";
_wp setWaypointLoiterRadius ([500, 1000] select ((vehicle leader _group) isKindOf "Plane"));
_group setCombatMode "YELLOW";
