/*
	NAME: brmh_cmd_fnc_boardOn
	DESCRIPTION: Those boarding who are in the vehicle now.
	PARAMETERS:
		0 - The squad's boarding machine (HASHMAP object)
	USAGE:
		private _names = ([_machine] call brmh_cmd_fnc_boardOn) apply { name _x };
	RETURNS: Soldiers (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
((_machine get "LIST") apply {
	_x # 0
}) select {
	alive _x and {
		vehicle _x isEqualTo (_machine get "VEHICLE")
	}
}
