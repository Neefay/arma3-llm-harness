params ["_machine"];
private _vehicle = _machine get "VEHICLE";
([_machine] call brmh_cmd_fnc_boardWaiting) findIf {
	_x params ["_man", "_role", "_cargo", "_turret"];
	((fullCrew [_vehicle, "", true]) findIf {
		alive (_x # 0) and {
			(_x # 0) isNotEqualTo _man
		} and {
			(_x # 1) isEqualTo _role
		} and {
			(_x # 2) isEqualTo _cargo
		} and {
			(_x # 3) isEqualTo _turret
		}
	}) >= 0
} >= 0
