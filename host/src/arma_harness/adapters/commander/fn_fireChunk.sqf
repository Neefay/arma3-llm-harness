params ["_mission"];
private _gun = _mission get "gun";
private _aim = _mission get "aim";
private _left = (_mission get "want") - (_mission getOrDefault ["fired", 0]);
private _radius = _mission get "radius";
// A spread is one round to a point. A mission can't outrun its magazine, so the step sends the rest.
private _at = if (_radius > 0) then {
	_aim getPos [random _radius, random 360]
} else {
	_aim
};
_gun doArtilleryFire [_at, _mission get "mag", [_left, 1] select (_radius > 0)];
_mission set ["issued", time];
_mission set ["firedAtIssue", _mission getOrDefault ["fired", 0]];
