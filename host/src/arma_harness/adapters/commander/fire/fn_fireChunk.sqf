/*
	NAME: brmh_cmd_fnc_fireChunk
	DESCRIPTION: Gives a gun the next order of its fire mission: every round still wanted, at the aim point, or with a
		radius, one round at a random point within it. It notes when the order went and how many had been fired by
		then, which the fire machine reads to tell when the order is done.
	PARAMETERS:
		0 - Mission record: gun, aim, want, radius, mag, and fired once it has (HASHMAP)
	USAGE:
		[_mission] call brmh_cmd_fnc_fireChunk;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_mission"];
private _gun = _mission get "gun";
private _aim = _mission get "aim";
private _left = (_mission get "want") - (_mission getOrDefault ["fired", 0]);
private _radius = _mission get "radius";
// A spread is one round to a point. A mission can't outrun its magazine, so the step sends the rest.
private _at = if (_radius > 0) then {
	_aim getPos [_radius * sqrt random 1, random 360]
} else {
	_aim
};
_gun doArtilleryFire [_at, _mission get "mag", [_left, 1] select (_radius > 0)];
_mission set ["issued", time];
_mission set ["firedAtIssue", _mission getOrDefault ["fired", 0]];
