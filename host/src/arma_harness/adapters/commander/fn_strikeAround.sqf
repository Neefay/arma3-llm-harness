// Round again: back out to the run-in point, and in on the same heading.
params ["_machine"];
private _group = _machine get "GROUP";
_machine set ["PASSES", (_machine get "PASSES") + 1];
_machine set ["DIRECT", false];
[_group] call brmh_cmd_fnc_clearRoute;
(_group addWaypoint [_machine get "IP", 0]) setWaypointType "MOVE";
