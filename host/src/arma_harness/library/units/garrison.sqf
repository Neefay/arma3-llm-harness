/*
	NAME: garrison
	DESCRIPTION: Put a group's men inside the buildings around a place, one to a building position, and keep them
		there: they turn and shoot, but don't leave. Only buildings with more than three positions are used.
	PARAMETERS:
		0 - group (GROUP): whose men, such as a spawn_group handle
		1 - at (POSITION, default "player"): the middle of the area
		2 - radius (NUMBER, default 120): how far from it to look for buildings, in m
	RETURNS: [men placed, buildings used] (ARRAY)
	TARGET: server
	TAGS: buildings, garrison, houses, inside, hide, defend, units
	EXAMPLE: {"group": "player", "radius": 60}
*/
params ["_group", "_at", "_radius"];
if (isNull _group) exitWith {
	"ERROR: no such group"
};
if (_at isEqualTo []) exitWith {
	"ERROR: no such place"
};
private _spots = [];
{
	_spots append (_x buildingPos -1);
} forEach ((nearestObjects [_at, ["House"], _radius]) select {
	count (_x buildingPos -1) > 3
});
if (_spots isEqualTo []) exitWith {
	format ["ERROR: no building with room for men within %1 m", _radius]
};
_spots = _spots call BIS_fnc_arrayShuffle;
private _placed = 0;
private _buildings = [];
{
	if (_forEachIndex >= count _spots) exitWith {};
	private _spot = _spots # _forEachIndex;
	_x setPosATL _spot;
	_x disableAI "PATH";
	_buildings pushBackUnique (nearestBuilding _spot);
	_placed = _placed + 1;
} forEach ((units _group) select {
	alive _x and {not isPlayer _x}
});
[_placed, count _buildings]
