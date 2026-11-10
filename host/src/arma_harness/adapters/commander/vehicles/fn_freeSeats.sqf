/*
	NAME: brmh_cmd_fnc_freeSeats
	DESCRIPTION: Free seats of a kind, in the game's own order. A seat with a dead man in it counts as free: the engine
		lets someone take it.
	PARAMETERS:
		0 - Vehicle (OBJECT)
		1 - Kind, as fullCrew names it: "driver", "gunner", "commander", "turret" or "cargo" (STRING)
	USAGE:
		[_vehicle, "cargo"] call brmh_cmd_fnc_freeSeats;
	RETURNS: fullCrew rows [unit, role, cargo index, turret path, ...] (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
params ["_vehicle", "_kind"];
(fullCrew [_vehicle, "", true]) select {
	(_x # 1) isEqualTo _kind and {
		isNull (_x # 0) or {
			not alive (_x # 0)
		}
	}
}
