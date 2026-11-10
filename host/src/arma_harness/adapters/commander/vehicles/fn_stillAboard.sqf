// Those of the squad still aboard what it's getting off.
params ["_machine"];
private _key = _machine get "KEY";
(units (_machine get "GROUP")) select {
	[_x] call brmh_cmd_fnc_able and {
		vehicle _x isNotEqualTo _x
	} and {
		_key isEqualTo "" or {
			(vehicle _x getVariable ["brmh_cmd_key", ""]) isEqualTo _key
		}
	}
}
