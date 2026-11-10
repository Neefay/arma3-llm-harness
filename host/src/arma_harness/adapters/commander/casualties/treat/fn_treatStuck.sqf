// He's stopped short, or hasn't moved in 20 s: time for another way in.
params ["_job"];
[_job] call brmh_cmd_fnc_treatReady or {
	(time - (_job get "MOVED")) >= 20
}
