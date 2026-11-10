// Whether there's still a place he hasn't tried to reach the man from.
params ["_carry"];
(_carry get "TRIES") < count ([_carry get "SUBJECT", getPosATL (_carry get "MEDIC")] call brmh_cmd_fnc_nearBody)
