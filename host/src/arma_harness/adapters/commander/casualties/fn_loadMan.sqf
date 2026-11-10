/*
	NAME: brmh_cmd_fnc_loadMan
	DESCRIPTION: Puts a man in a vehicle's first free cargo seat. Not ACE's own loading: that moves a man to a new group
		if the vehicle is empty, and he'd vanish from his squad until unloaded.
	PARAMETERS:
		0 - Man (OBJECT)
		1 - Vehicle (OBJECT)
	USAGE:
		[_casualty, _vehicle] call brmh_cmd_fnc_loadMan;
	RETURNS: Whether there was a seat for him (BOOL)
	ENVIRONMENT: Server, unscheduled. The man has to be local
*/
params ["_man", "_vehicle"];
private _cargo = fullCrew [_vehicle, "cargo", true];
// Firing-from-vehicle seats are cargo seats too, but fullCrew "cargo" leaves them out (as ACE's loadPersonLocal notes).
if (_cargo isEqualTo []) then {
	_cargo = (fullCrew [_vehicle, "turret", true]) select {
		_x # 4
	};
};
private _seats = _cargo select {
	isNull (_x # 0)
};
if (_seats isEqualTo []) exitWith {
	false
};
_man assignAsCargoIndex [_vehicle, _seats # 0 # 2];
_man moveInCargo [_vehicle, _seats # 0 # 2];
true
