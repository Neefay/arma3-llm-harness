/*
	NAME: brmh_cmd_fnc_knockDown
	DESCRIPTION: Puts men of a station down, as if hit, for a scenario that wants casualties without a fight. Never its
		leader. Needs ACE's medical system. Operator action.
	PARAMETERS:
		0 - Callsign (STRING)
		1 - (OPTIONAL) How many (NUMBER) - Default: 1
	USAGE:
		["Alpha", 2] call brmh_cmd_fnc_knockDown;
	RETURNS: true
	ENVIRONMENT: Server
*/
params [["_callsign", "", [""]], ["_count", 1, [0]]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
private _men = (units _group) select {
	[_x] call brmh_cmd_fnc_able and {
		_x isNotEqualTo leader _group
	}
};
{
	[_x, 0.4, "body", "bullet"] call ace_medical_fnc_addDamageToUnit;
	[_x, true, 0, false] call ace_medical_fnc_setUnconscious;
} forEach (_men select [0, _count]);
true
