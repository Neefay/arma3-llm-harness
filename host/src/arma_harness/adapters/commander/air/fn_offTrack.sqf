// Degrees between where an aircraft is going and a point, from its velocity: its nose can point 10-15° off its track.
params ["_vehicle", "_at"];
private _velocity = velocity _vehicle;
private _to = (_at vectorDiff getPosASL _vehicle);
acos ((((vectorNormalized [_velocity # 0, _velocity # 1, 0]) vectorDotProduct (vectorNormalized [_to # 0, _to # 1, 0])) min 1) max -1)
