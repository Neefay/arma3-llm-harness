/*
	NAME: brmh_cmd_fnc_targets
	DESCRIPTION: The men an order names, from the host's rows. A key whose man no longer exists, such as a deleted body,
		is left out.
	PARAMETERS:
		0 - Rows: [[man key, place], ...] (ARRAY)
	USAGE:
		private _men = [_who] call brmh_cmd_fnc_targets;
	RETURNS: The men (ARRAY of OBJECT)
	ENVIRONMENT: Server, unscheduled
*/
params ["_rows"];
(_rows apply {
	brmh_cmd_men getOrDefault [_x # 0, objNull]
}) select {
	not isNull _x
}
