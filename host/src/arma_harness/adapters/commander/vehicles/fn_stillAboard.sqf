/*
	NAME: brmh_cmd_fnc_stillAboard
	DESCRIPTION: Those of a squad still aboard what it's getting off: one vehicle, or any if no vehicle was named.
	PARAMETERS:
		0 - The squad's boarding machine, getting off (HASHMAP object)
	USAGE:
		if (([_machine] call brmh_cmd_fnc_stillAboard) isEqualTo []) then { ... };
	RETURNS: Soldiers (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
private _key = _machine get "KEY";
(units (_machine get "GROUP")) select {
	[_x] call brmh_cmd_fnc_able and {
		not isNull objectParent _x
	} and {
		_key isEqualTo "" or {
			(vehicle _x getVariable ["brmh_cmd_key", ""]) isEqualTo _key
		}
	}
}
