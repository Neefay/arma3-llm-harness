/*
	NAME: brmh_cmd_fnc_holdAir
	DESCRIPTION: An aircraft circles a place until it's needed: a left-hand circle 500 m across for a helicopter, 1 km
		for a plane, free to fire at what it meets. The place is kept as its hold, where strikes and sorties send it
		back to.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Position [x, y] or [x, y, z] (ARRAY)
	USAGE:
		[_group, [2500, 1500]] call brmh_cmd_fnc_holdAir;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params [["_group", grpNull, [grpNull]], ["_at", [], [[]], [2, 3]]];
_group setVariable ["brmh_cmd_hold", _at];
[_group] call brmh_cmd_fnc_clearRoute;
private _wp = _group addWaypoint [(_at select [0, 2]) + [0], 0];
_wp setWaypointType "LOITER";
_wp setWaypointLoiterType "CIRCLE_L";
_wp setWaypointLoiterRadius ([500, 1000] select ((vehicle leader _group) isKindOf "Plane"));
_group setCombatMode "YELLOW";
