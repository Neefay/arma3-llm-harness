params ["_man"];
private _vehicle = vehicle _man;
if (_vehicle isNotEqualTo _man) then {
	_man action ["GetOut", _vehicle];
};
unassignVehicle _man;
[_man] orderGetIn false;
_man enableAI "TARGET";
