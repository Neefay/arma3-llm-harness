// Tries the next place he could reach the man from.
params ["_carry"];
private _tries = _carry get "TRIES";
private _spots = [_carry get "SUBJECT", getPosATL (_carry get "MEDIC")] call brmh_cmd_fnc_nearBody;
if (_tries < count _spots) then {
	(_carry get "MEDIC") doMove (_spots # _tries);
};
_carry set ["TRIES", _tries + 1];
_carry set ["ORDERED", time];
_carry set ["MOVED", time];
