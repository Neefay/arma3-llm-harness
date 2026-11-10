// Time for another way in: he's stopped short, or hasn't moved in 20 s.
params ["_carry"];
[_carry] call brmh_cmd_fnc_carryReady or {
	(time - (_carry get "MOVED")) >= 20
}
