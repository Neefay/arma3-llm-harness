/*
	NAME: brmh_cmd_fnc_treatArrived
	DESCRIPTION: Whether a medic is close enough to start: within 3 m of the man, or 8 m of the vehicle he's in, or
		stopped within 8 m of him (a house position can stop him a few metres short).
	PARAMETERS:
		0 - The medic's job, a treat machine (HASHMAP object)
	USAGE:
		if ([_job] call brmh_cmd_fnc_treatArrived) then { [_job] call brmh_cmd_fnc_treatStart };
	RETURNS: BOOL
	ENVIRONMENT: Server, unscheduled
*/
params ["_job"];
private _away = (_job get "MEDIC") distance (vehicle (_job get "SUBJECT"));
_away <= ([3, 8] select ([_job] call brmh_cmd_fnc_treatAboard)) or {
	_away <= 8 and {
		[_job] call brmh_cmd_fnc_treatReady or {
			(time - (_job get "MOVED")) >= 8
		}
	}
}
