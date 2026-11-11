/*
	NAME: arrow_above
	DESCRIPTION: A big coloured arrow floating above something, pointing at it, to show the player what you mean.
		Remove it with delete_made.
	PARAMETERS:
		0 - target (OBJECT): what to point at
		1 - colour (STRING, default "Blue"): Blue, Red, Green, Yellow, Orange, Pink, Cyan, White or Purple
		2 - height (NUMBER, default 4): how far above it, in m
	RETURNS: handle (STRING)
	TARGET: server
	TAGS: arrow, marker, point, highlight, show, indicate
	EXAMPLE: {"target": "player", "colour": "Green"}
*/
params ["_target", "_colour", "_height"];
if (isNull _target) exitWith {
	"ERROR: nothing to point at"
};
private _class = format ["Sign_Arrow_Large_%1_F", _colour];
if (not isClass (configFile >> "CfgVehicles" >> _class)) exitWith {
	format ["ERROR: no %1 arrow: try Blue, Red, Green, Yellow, Orange, Pink, Cyan, White or Purple", _colour]
};
private _arrow = createVehicle [_class, [0, 0, 0], [], 0, "CAN_COLLIDE"];
_arrow setPosATL ((getPosATL _target) vectorAdd [0, 0, _height]);
[[_arrow], format ["arrow over %1", name _target]] call brmh_lib_fnc_keep
