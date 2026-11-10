// Close enough to start: beside him, or at the vehicle he's in, or stopped within 8 m.
params ["_job"];
private _away = (_job get "MEDIC") distance (vehicle (_job get "SUBJECT"));
_away <= ([3, 8] select ([_job] call brmh_cmd_fnc_treatAboard)) or {
	_away <= 8 and {
		[_job] call brmh_cmd_fnc_treatReady or {
			(time - (_job get "MOVED")) >= 8
		}
	}
}
