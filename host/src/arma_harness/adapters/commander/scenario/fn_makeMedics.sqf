/*
	NAME: brmh_cmd_fnc_makeMedics
	DESCRIPTION: Makes the last men of a station's list medics, for ACE and for the engine both. Operator action, from
		the scenario.
	PARAMETERS:
		0 - Callsign (STRING)
		1 - How many (NUMBER)
	USAGE:
		["Alpha", 1] call brmh_cmd_fnc_makeMedics;
	RETURNS: true
	ENVIRONMENT: Server
*/
params [["_callsign", "", [""]], ["_count", 0, [0]]];
private _men = +(units (brmh_cmd_stations get _callsign));
reverse _men;
{
	_x setVariable ["ace_medical_medicClass", 1, true];
	_x setUnitTrait ["medic", true];
} forEach (_men select [0, _count]);
true
