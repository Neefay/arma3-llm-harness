/*
	NAME: brmh_cmd_fnc_placedState
	DESCRIPTION: What a squad's placing machine (OCCUPY or CORDON) is at, for the packet's "placed" field.
	PARAMETERS:
		0 - Squad (GROUP)
	USAGE:
		["placed", [_group] call brmh_cmd_fnc_placedState]
	RETURNS: -1 with none running, 0 while moving, 1 once placed (NUMBER)
	ENVIRONMENT: Server, unscheduled
*/
params ["_group"];
private _at = brmh_cmd_builds findIf {
	(_x get "GROUP") isEqualTo _group and {
		((_x get "SPEC") get "KIND") isEqualTo "placing"
	} and {
		(_x get "STATE") isNotEqualTo ""
	}
};
if (_at < 0) exitWith {
	-1
};
parseNumber (((brmh_cmd_builds # _at) get "STATE") isEqualTo "placed")
