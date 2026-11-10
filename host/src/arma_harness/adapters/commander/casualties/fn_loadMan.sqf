// ACE's own loading moves a man to a new group if the vehicle is empty, and he'd vanish from his squad until unloaded.
params ["_man", "_vehicle"];
private _seats = (fullCrew [_vehicle, "cargo", true]) select {
	isNull (_x # 0)
};
if (_seats isEqualTo []) exitWith {
	false
};
_man assignAsCargoIndex [_vehicle, _seats # 0 # 2];
_man moveInCargo [_vehicle, _seats # 0 # 2];
true
