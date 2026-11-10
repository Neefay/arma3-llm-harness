/*
	NAME: brmh_cmd_fnc_able
	DESCRIPTION: Whether a man can do anything: alive and conscious. Under ACE a downed man is alive, and stays in his
		group, lying where he fell, so alive alone would count him.
	PARAMETERS:
		0 - The man (OBJECT)
	USAGE:
		private _fit = (units _group) select { [_x] call brmh_cmd_fnc_able };
	RETURNS: Whether he's alive and not incapacitated (BOOL)
	ENVIRONMENT: Any machine, unscheduled or scheduled
*/
params ["_man"];
alive _man and {
	lifeState _man isNotEqualTo "INCAPACITATED"
}
