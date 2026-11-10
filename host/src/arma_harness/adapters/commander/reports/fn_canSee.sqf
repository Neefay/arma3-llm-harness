/*
	NAME: brmh_cmd_fnc_canSee
	DESCRIPTION: Whether any of these soldiers has a line of sight from his eyes to a point. Only the line is tested,
		not light, fog or distance, so callers keep the range down themselves.
	PARAMETERS:
		0 - Soldiers looking (ARRAY of OBJECTs)
		1 - The object at the point, left out of the test so it can't hide itself, or objNull (OBJECT)
		2 - Point, ASL (ARRAY)
		3 - (OPTIONAL) LOD tested against: "VIEW" is blocked by smoke, "FIRE" isn't (STRING) - Default: "VIEW"
	USAGE:
		[_lookers, _vehicle, (getPosASL _vehicle) vectorAdd [0, 0, 1], "FIRE"] call brmh_cmd_fnc_canSee;
	RETURNS: true if any of them has visibility above 0.3 (BOOL)
	ENVIRONMENT: Server, unscheduled
*/
params ["_soldiers", "_object", "_point", ["_through", "VIEW"]];
(_soldiers findIf {
	// From the vehicle he's in, if any: its own hull isn't in the way (as LAMBS checks).
	([vehicle _x, _through, _object] checkVisibility [eyePos vehicle _x, _point]) > 0.3
}) >= 0
