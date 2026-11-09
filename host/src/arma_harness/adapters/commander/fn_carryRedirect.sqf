// A new place for a man already on the way, or on someone's shoulder.
params ["_carry", "_place", "_order"];
_carry set ["TO", _place];
_carry set ["ORDER", _order];
_carry set ["MOVED", time];
private _dummy = _carry getOrDefault ["DUMMY", objNull];
if (not isNull _dummy) then {
	_dummy doMove ([_carry] call brmh_cmd_fnc_carryPlace);
};
