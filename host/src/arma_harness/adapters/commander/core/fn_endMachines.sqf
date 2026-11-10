/*
	NAME: brmh_cmd_fnc_endMachines
	DESCRIPTION: Ends a squad's machines of these kinds, as a new order does to the old one's. Each says its word and
		runs its RELEASE; brmh_cmd_fnc_stepBuilds drops them from brmh_cmd_builds on its next step.
	PARAMETERS:
		0 - Squad (GROUP)
		1 - Kinds to end, as their declarations' KIND (ARRAY of STRING)
		2 - (OPTIONAL) The word they end with (STRING) - Default: "called off"
	USAGE:
		[_group, ["placing", "clearing"]] call brmh_cmd_fnc_endMachines;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_group", "_kinds", ["_word", "called off"]];
{
	if ((_x get "GROUP") isEqualTo _group and {
		((_x get "SPEC") get "KIND") in _kinds
	}) then {
		_x call ["#END", [_word]];
	};
} forEach brmh_cmd_builds;
