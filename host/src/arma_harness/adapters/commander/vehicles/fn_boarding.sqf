/*
	NAME: brmh_cmd_fnc_boarding
	DESCRIPTION: A squad's boarding machine that's still running, getting on or getting off, or nil.
	PARAMETERS:
		0 - Group (GROUP)
	USAGE:
		private _machine = [_group] call brmh_cmd_fnc_boarding;
	RETURNS: The machine (HASHMAP object), or nil
	ENVIRONMENT: Server, unscheduled
*/
params ["_group"];
private _at = brmh_cmd_builds findIf {
	(_x get "GROUP") isEqualTo _group and {
		((_x get "SPEC") get "KIND") isEqualTo "boarding"
	} and {
		(_x get "STATE") isNotEqualTo ""
	}
};
if (_at < 0) then {
	nil
} else {
	brmh_cmd_builds # _at
}
