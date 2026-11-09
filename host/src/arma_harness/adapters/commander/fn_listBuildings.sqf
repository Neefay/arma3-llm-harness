params [["_at", [], [[]], 2], ["_radius", 400, [0]]];
private _centre = _at + [0];
(nearestObjects [_centre, ["House"], _radius] select {
	count (_x buildingPos -1) > 0
}) apply {
	private _box = boundingBoxReal _x;
	private _size = (_box # 1) vectorDiff (_box # 0);
	private _position = getPosATL _x;
	[_position # 0, _position # 1, mapGridPosition _position, getText (configOf _x >> "displayName"), count (_x buildingPos -1), _size # 0, _size # 1, getDir _x]
}
