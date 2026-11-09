/*
	NAME: brmh_cmd_fnc_listBuildings
	DESCRIPTION: The world's buildings with positions in them, around a place, for the commander's numbered list.
	PARAMETERS:
		0 - Centre [x, y] (ARRAY)
		1 - (OPTIONAL) Radius, metres (NUMBER) - Default: 400
	USAGE:
		[[4150, 4150], 400] call brmh_cmd_fnc_listBuildings;
	RETURNS: [[x, y, grid, display name, positions, width, length, direction], ...] (ARRAY)
	ENVIRONMENT: Server
*/
params [["_at", [], [[]], 2], ["_radius", 400, [0]]];
private _centre = _at + [0];
(nearestObjects [_centre, ["House"], _radius] select {
	(_x buildingPos -1) isNotEqualTo []
}) apply {
	private _box = boundingBoxReal _x;
	private _size = (_box # 1) vectorDiff (_box # 0);
	private _position = getPosATL _x;
	[_position # 0, _position # 1, mapGridPosition _position, getText (configOf _x >> "displayName"), count (_x buildingPos -1), _size # 0, _size # 1, getDir _x]
}
