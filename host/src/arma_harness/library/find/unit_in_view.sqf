/*
	NAME: unit_in_view
	DESCRIPTION: The man the player is looking at: "this guy", "him". The nearest to the middle of the screen,
		within a cone in front of the camera. Runs on the player's own machine.
	PARAMETERS:
		0 - range (NUMBER, default 80): the farthest to look, in m
	RETURNS: {name, class, net id, distance in m, side} (HASHMAP), or "nobody"
	TARGET: interface
	TAGS: this guy, him, look, aim, view, target, unit, crosshair, find
	EXAMPLE: {}
*/
params ["_range"];
private _eye = positionCameraToWorld [0, 0, 0];
private _ahead = _eye vectorFromTo (positionCameraToWorld [0, 0, 100]);
private _seen = ((player nearEntities ["CAManBase", _range]) - [player]) apply {
	private _towards = (getPosATL _x) vectorDiff (getPosATL player);
	[(_towards vectorDotProduct _ahead) / ((vectorMagnitude _towards) max 0.1), _x]
} select {
	(_x # 0) > 0.8
};
_seen sort false;
if (_seen isEqualTo []) exitWith {
	"nobody"
};
private _man = (_seen # 0) # 1;
createHashMapFromArray [
	["name", name _man],
	["class", typeOf _man],
	["netId", netId _man],
	["distance", round (player distance _man)],
	["side", str side group _man]
]
