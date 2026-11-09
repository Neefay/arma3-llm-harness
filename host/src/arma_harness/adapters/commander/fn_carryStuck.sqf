params ["_carry"];
[_carry] call brmh_cmd_fnc_carryReady or {
	(time - (_carry get "MOVED")) >= 20
}
