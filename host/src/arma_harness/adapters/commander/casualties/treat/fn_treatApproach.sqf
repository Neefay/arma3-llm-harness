/*
	NAME: brmh_cmd_fnc_treatApproach
	DESCRIPTION: The medic heads for the next place he could reach the man from: a random spot 4 m from the vehicle
		he's in, or the next of brmh_cmd_fnc_nearBody's places. Counts the try.
	PARAMETERS:
		0 - Treat job (HASHMAP object)
	USAGE:
		[_job] call brmh_cmd_fnc_treatApproach;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_job"];
private _man = _job get "SUBJECT";
private _medic = _job get "MEDIC";
private _tries = _job get "TRIES";
if ([_job] call brmh_cmd_fnc_treatAboard) then {
	_medic doMove ((vehicle _man) getPos [4, random 360]);
} else {
	private _spots = [_man, getPosATL _medic] call brmh_cmd_fnc_nearBody;
	if (_tries < count _spots) then {
		_medic doMove (_spots # _tries);
	};
};
_job set ["TRIES", _tries + 1];
_job set ["ORDERED", time];
_job set ["MOVED", time];
