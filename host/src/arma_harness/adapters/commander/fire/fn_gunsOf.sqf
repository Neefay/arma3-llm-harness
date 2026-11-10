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
