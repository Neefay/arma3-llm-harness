/*
	NAME: brmh_cmd_fnc_friendly
	DESCRIPTION: Whether a man is on the squad's side. Goes by his group's side, not his own: ACE can make a man who's
		down captive, which changes his. The enemy's downed are never carried, treated or listed.
	PARAMETERS:
		0 - Squad (GROUP)
		1 - The man (OBJECT)
	USAGE:
		private _ours = brmh_cmd_down select { [_group, _x] call brmh_cmd_fnc_friendly };
	RETURNS: Whether his side is friendly to the squad's (BOOL)
	ENVIRONMENT: Any machine, unscheduled or scheduled
*/
params ["_group", "_man"];
((side _group) getFriend (side group _man)) >= 0.6
