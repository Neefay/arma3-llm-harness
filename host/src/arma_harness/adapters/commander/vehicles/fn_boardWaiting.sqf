/*
	NAME: brmh_cmd_fnc_boardWaiting
	DESCRIPTION: Those boarding still on their way to their seats. Not a man downed on the way: he isn't coming, and
		the rest shouldn't wait for him.
	PARAMETERS:
		0 - The squad's boarding machine (HASHMAP object)
	USAGE:
		if (([_machine] call brmh_cmd_fnc_boardWaiting) isEqualTo []) then { ... };
	RETURNS: [man, role, cargo index, turret path] rows, as the machine's LIST holds them (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
(_machine get "LIST") select {
	[_x # 0] call brmh_cmd_fnc_able and {
		vehicle (_x # 0) isNotEqualTo (_machine get "VEHICLE")
	}
}
