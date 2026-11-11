/*
	NAME: teleport
	DESCRIPTION: Move someone, with their vehicle if they're in one, to a place, on clear ground near it.
	PARAMETERS:
		0 - to (POSITION): where
		1 - who (OBJECT, default "player"): who
	RETURNS: the grid they're now at (STRING)
	TARGET: server
	TAGS: teleport, move, travel, position, go
	EXAMPLE: {"to": "player"}
*/
params ["_to", "_who"];
if (isNull _who) exitWith {
	"ERROR: no such unit"
};
if (_to isEqualTo []) exitWith {
	"ERROR: no such place: give [x, y], a grid such as 034 030, or a unit"
};
private _moving = vehicle _who;
private _at = _to findEmptyPosition [0, 30, typeOf _moving];
if (_at isEqualTo []) then {
	_at = _to;
};
_moving setVehiclePosition [_at, [], 0, "NONE"];
mapGridPosition _moving
