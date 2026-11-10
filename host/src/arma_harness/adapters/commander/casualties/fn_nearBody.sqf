/*
	NAME: brmh_cmd_fnc_nearBody
	DESCRIPTION: Where to send someone who has to reach a downed man, best first. The pathfinder often can't get to him.
		With a body at some spots in a house, nowhere in or right beside that house can be planned to, though it's fine
		with the body elsewhere, and open ground is fine either way. A man told to go there stands still for 12 s, then
		reports himself ready. So: the nearest position of the house at his level, the man himself, then a ring clear of
		the house, nearest the rescuer first.
	PARAMETERS:
		0 - Downed man (OBJECT)
		1 - Where the rescuer is (ARRAY)
	USAGE:
		private _spots = [_casualty, getPosATL _medic] call brmh_cmd_fnc_nearBody;
	RETURNS: Positions ATL, best first: one house position at most, the body's own, then eight around (ARRAY)
	ENVIRONMENT: Any machine. Used on the server, unscheduled
*/
params ["_body", "_from"];
private _at = getPosATL _body;
private _level = ((nearestObject [_body, "House"]) buildingPos -1) select {
	(_x distance _at) < 6 and {
		abs ((_x # 2) - (_at # 2)) < 1.5
	}
};
_level = _level apply {
	[_x distance _at, _x]
};
_level sort true;
// 14 m wasn't enough from the middle of the largest house here, and 26 m was.
private _clear = [12, 25] select (_level isNotEqualTo []);
private _ring = [0, 45, 90, 135, 180, 225, 270, 315] apply {
	private _spot = _at getPos [_clear, _x];
	[_spot distance2D _from, [_spot # 0, _spot # 1, 0]]
};
_ring sort true;
((_level select [0, 1]) apply {
	_x # 1
}) + [_at] + (_ring apply {
	_x # 1
})
