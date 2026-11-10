/*
	NAME: brmh_cmd_fnc_clearRoute
	DESCRIPTION: Deletes all of a squad's waypoints, last first, so no index moves under the loop. It doesn't stop a
		squad that's walking: doStop does.
	PARAMETERS:
		0 - Squad (GROUP)
	USAGE:
		[_group] call brmh_cmd_fnc_clearRoute;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_group"];
for "_i" from (count waypoints _group - 1) to 0 step -1 do {
	deleteWaypoint [_group, _i];
};
