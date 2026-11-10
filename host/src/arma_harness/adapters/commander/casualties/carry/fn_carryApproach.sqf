/*
	NAME: brmh_cmd_fnc_carryApproach
	DESCRIPTION: Sends the bearer to the next place he could reach the man from (brmh_cmd_fnc_nearBody), and counts
		the try. Once every place has been tried he isn't moved again, and the machine decides what's next.
	PARAMETERS:
		0 - Carry (HASHMAP object)
	USAGE:
		[_carry] call brmh_cmd_fnc_carryApproach;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_carry"];
private _tries = _carry get "TRIES";
private _spots = [_carry get "SUBJECT", getPosATL (_carry get "MEDIC")] call brmh_cmd_fnc_nearBody;
if (_tries < count _spots) then {
	(_carry get "MEDIC") doMove (_spots # _tries);
};
_carry set ["TRIES", _tries + 1];
_carry set ["ORDERED", time];
_carry set ["MOVED", time];
