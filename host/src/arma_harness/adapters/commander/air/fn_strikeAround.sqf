/*
	NAME: brmh_cmd_fnc_strikeAround
	DESCRIPTION: Round again, after a first run that passed the grid without a release: back out to the run-in point,
		and in on the same heading. The pass is counted, so a second miss ends the strike.
	PARAMETERS:
		0 - Strike machine (HASHMAP object)
	USAGE:
		[_this] call brmh_cmd_fnc_strikeAround;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. The strike machine's "going around" action.
*/
params ["_machine"];
private _group = _machine get "GROUP";
_machine set ["PASSES", (_machine get "PASSES") + 1];
_machine set ["DIRECT", false];
[_group] call brmh_cmd_fnc_clearRoute;
(_group addWaypoint [_machine get "IP", 0]) setWaypointType "MOVE";
