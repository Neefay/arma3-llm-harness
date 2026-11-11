/*
	NAME: measure_class
	DESCRIPTION: An object's size, measured from its model, before laying things out with it. The length is along
		the model's x axis: east-west at direction 0, north-south at 90.
	PARAMETERS:
		0 - class (STRING): the object's class
	RETURNS: [length, width, height] in m (ARRAY)
	TARGET: server
	TAGS: measure, size, dimensions, bounding box, build, layout, object
	EXAMPLE: {"class": "Land_HBarrier_5_F"}
*/
params ["_class"];
if (not isClass (configFile >> "CfgVehicles" >> _class)) exitWith {
	format ["ERROR: there's no class %1", _class]
};
private _probe = _class createVehicleLocal [0, 0, 0];
private _box = boundingBoxReal _probe;
deleteVehicle _probe;
((_box # 1) vectorDiff (_box # 0)) apply {
	(round (_x * 10)) / 10
}
