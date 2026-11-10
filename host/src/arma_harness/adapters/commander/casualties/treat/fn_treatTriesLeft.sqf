/*
	NAME: brmh_cmd_fnc_treatTriesLeft
	DESCRIPTION: Whether a medic still has a way in to try: four places around a vehicle the man's in, or each of the
		spots beside his body (brmh_cmd_fnc_nearBody).
	PARAMETERS:
		0 - The medic's job, a treat machine (HASHMAP object)
	USAGE:
		if ([_job] call brmh_cmd_fnc_treatTriesLeft) then { [_job] call brmh_cmd_fnc_treatApproach };
	RETURNS: BOOL
	ENVIRONMENT: Server, unscheduled
*/
params ["_job"];
if ([_job] call brmh_cmd_fnc_treatAboard) exitWith {
	(_job get "TRIES") < 4
};
(_job get "TRIES") < count ([_job get "SUBJECT", getPosATL (_job get "MEDIC")] call brmh_cmd_fnc_nearBody)
