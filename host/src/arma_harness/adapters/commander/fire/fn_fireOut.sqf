/*
	NAME: brmh_cmd_fnc_fireOut
	DESCRIPTION: Whether a gun has nothing left of the type its mission fires, so an order that's done means it's
		out.
	PARAMETERS:
		0 - The gun's fire machine (HASHMAP object)
	USAGE:
		if ([_machine] call brmh_cmd_fnc_fireOut) then { [_machine, "out"] call brmh_cmd_fnc_fireFinish };
	RETURNS: BOOL
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
(([_machine get "GUN"] call brmh_cmd_fnc_gunAmmo) findIf {
	(_x # 0) isEqualTo ((_machine get "MISSION") get "word") and {
		(_x # 1) > 0
	}
}) < 0
