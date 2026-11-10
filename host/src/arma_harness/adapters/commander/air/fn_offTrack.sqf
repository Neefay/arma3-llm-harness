/*
	NAME: brmh_cmd_fnc_offTrack
	DESCRIPTION: Degrees between where an aircraft is going and a point, flat on the map. Taken from its velocity, not
		its nose, which can point 10-15° off its track.
	PARAMETERS:
		0 - Aircraft (OBJECT)
		1 - Point [x, y, z]; only x and y count (ARRAY)
	USAGE:
		([_vehicle, _machine get "AIM"] call brmh_cmd_fnc_offTrack) < 15
	RETURNS: 0 to 180 (NUMBER); 90 when it isn't moving
	ENVIRONMENT: Any, unscheduled
*/
params ["_vehicle", "_at"];
private _velocity = velocity _vehicle;
private _to = (_at vectorDiff getPosASL _vehicle);
acos ((((vectorNormalized [_velocity # 0, _velocity # 1, 0]) vectorDotProduct (vectorNormalized [_to # 0, _to # 1, 0])) min 1) max -1)
