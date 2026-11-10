/*
	NAME: brmh_cmd_fnc_strikePassed
	DESCRIPTION: Whether the aircraft is past the grid without releasing: over it (within 300 m), or with it behind him
		(more than 90° off his track) within 3 km.
	PARAMETERS:
		0 - Strike machine (HASHMAP object)
	USAGE:
		[_this] call brmh_cmd_fnc_strikePassed
	RETURNS: Boolean
	ENVIRONMENT: Server, unscheduled. The strike machine's guards on the run.
*/
params ["_machine"];
private _vehicle = _machine get "VEHICLE";
private _aim = _machine get "AIM";
private _distance = _vehicle distance2D _aim;
_distance < 300 or {
	_distance < 3000 and {
		([_vehicle, _aim] call brmh_cmd_fnc_offTrack) > 90
	}
}
