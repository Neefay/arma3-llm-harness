/*
	NAME: brmh_cmd_fnc_gunsOf
	DESCRIPTION: The guns an order names, or with none named, every artillery piece the station has a gunner on. A
		named gun is looked up as it is, whoever crews it, and a key that isn't known comes back as objNull, so the
		caller can say why it can't fire.
	PARAMETERS:
		0 - Group (GROUP)
		1 - Gun keys, or [] for the station's own (ARRAY)
	USAGE:
		[_group, []] call brmh_cmd_fnc_gunsOf;
		[_group, ["V1", "V2"]] call brmh_cmd_fnc_gunsOf;
	RETURNS: The guns (ARRAY of OBJECTs)
	ENVIRONMENT: Server, unscheduled
*/
params ["_group", "_keys"];
if (_keys isNotEqualTo []) exitWith {
	_keys apply {
		brmh_cmd_vehicles getOrDefault [_x, objNull]
	}
};
private _guns = [];
{
	private _vehicle = vehicle _x;
	if (_vehicle isNotEqualTo _x and {
		gunner _vehicle isEqualTo _x
	} and {
		getNumber (configOf _vehicle >> "artilleryScanner") > 0
	}) then {
		_guns pushBackUnique _vehicle;
	};
} forEach units _group;
_guns
