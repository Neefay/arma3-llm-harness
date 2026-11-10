/*
	NAME: brmh_cmd_fnc_killStation
	DESCRIPTION: Kills a station's men where they stand, for a scenario event or a test of losing one. Operator action.
	PARAMETERS:
		0 - Callsign (STRING)
	USAGE:
		["Alpha"] call brmh_cmd_fnc_killStation;
	RETURNS: true
	ENVIRONMENT: Server, unscheduled
*/
params [["_callsign", "", [""]]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
{
	_x setDamage 1;
} forEach units _group;
true
