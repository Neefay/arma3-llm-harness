params ["_machine"];
(([_machine get "GUN"] call brmh_cmd_fnc_gunAmmo) findIf {
	(_x # 0) isEqualTo ((_machine get "MISSION") get "word") and {
		(_x # 1) > 0
	}
}) < 0
