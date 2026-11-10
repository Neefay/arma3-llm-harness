/*
	NAME: brmh_cmd_fnc_boardTaken
	DESCRIPTION: Whether someone else has taken a seat that one of those boarding is still on his way to. The engine
		has a man wait beside a taken seat for good, with no error, so this is the only way to know.
	PARAMETERS:
		0 - The squad's boarding machine (HASHMAP object)
	USAGE:
		if ([_machine] call brmh_cmd_fnc_boardTaken) then { [_machine, "taken", []] call brmh_cmd_fnc_boardFinish };
	RETURNS: BOOL
	ENVIRONMENT: Server, unscheduled
*/
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
