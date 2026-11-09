// A squad's men who can do as they're told: able, and not carrying, treating or building.
params ["_group"];
(units _group) select {
	[_x] call brmh_cmd_fnc_able and {
		not (_x getVariable ["brmh_cmd_busy", false])
	}
}
