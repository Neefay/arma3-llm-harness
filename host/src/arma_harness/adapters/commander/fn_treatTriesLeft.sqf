// Places he can go to reach the man: around a vehicle he's in, or the spots beside the body.
params ["_job"];
if ([_job] call brmh_cmd_fnc_treatAboard) exitWith {
	(_job get "TRIES") < 4
};
(_job get "TRIES") < count ([_job get "SUBJECT", getPosATL (_job get "MEDIC")] call brmh_cmd_fnc_nearBody)
