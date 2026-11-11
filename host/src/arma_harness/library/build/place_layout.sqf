/*
	NAME: place_layout
	DESCRIPTION: Place objects from a layout around a centre, as simple objects: props with no simulation, so a
		campfire won't burn and a flag shows no cloth (use spawn_vehicle for anything that must work). Each entry is
		[class, [east offset, north offset, height], direction]; height is above the ground, such as 0.8 for an item
		on a camping table. Measure classes first with measure_class. Remove it all with delete_made.
	PARAMETERS:
		0 - center (POSITION): the layout's centre
		1 - layout (ARRAY): the entries, [class, [dx, dy, z], dir]
	RETURNS: [handle, placed, failed classes] (ARRAY)
	TARGET: server
	TAGS: build, place, layout, objects, props, outpost, camp, base, compose
	EXAMPLE: {"center": [0, 0], "layout": [["Land_HBarrier_5_F", [0, 0, 0], 90]]}
*/
params ["_center", "_layout"];
if (_center isEqualTo []) exitWith {
	"ERROR: no such place"
};
private _made = [];
private _failed = [];
{
	_x params [["_class", "", [""]], ["_offset", [0, 0, 0], [[]]], ["_dir", 0, [0]]];
	_offset params [["_east", 0, [0]], ["_north", 0, [0]], ["_up", 0, [0]]];
	if (not isClass (configFile >> "CfgVehicles" >> _class)) then {
		_failed pushBack _class;
	} else {
		// createSimpleObject wants the model centre's world position. A real object put where it should go gives it,
		// with its orientation on the slope, without working out the model's offset.
		private _probe = _class createVehicleLocal [0, 0, 0];
		_probe enableSimulation false;
		_probe setDir _dir;
		_probe setPosATL [(_center # 0) + _east, (_center # 1) + _north, _up];
		private _world = getPosWorld _probe;
		private _facing = [vectorDir _probe, vectorUp _probe];
		private _model = getText (configOf _probe >> "model");
		deleteVehicle _probe;
		private _object = createSimpleObject [_model, _world];
		if (isNull _object) then {
			_failed pushBack _class;
		} else {
			_object setVectorDirAndUp _facing;
			_made pushBack _object;
		};
	};
} forEach _layout;
private _handle = [_made, format ["layout of %1", count _made]] call brmh_lib_fnc_keep;
[_handle, count _made, _failed]
