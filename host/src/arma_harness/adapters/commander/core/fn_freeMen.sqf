/*
	NAME: brmh_cmd_fnc_freeMen
	DESCRIPTION: A squad's men who can do as they're told: able, and not carrying, treating or building (brmh_cmd_busy).
	PARAMETERS:
		0 - Squad (GROUP)
	USAGE:
		doStop ([_group] call brmh_cmd_fnc_freeMen);
	RETURNS: The men (ARRAY of OBJECT)
	ENVIRONMENT: Server, unscheduled
*/
params ["_group"];
(units _group) select {
	[_x] call brmh_cmd_fnc_able and {
		not (_x getVariable ["brmh_cmd_busy", false])
	}
}
