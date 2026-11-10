/*
	NAME: brmh_cmd_fnc_deleteStation
	DESCRIPTION: Removes a station's men from the game, for a scenario event. Operator action.
	PARAMETERS:
		0 - Callsign (STRING)
	USAGE:
		["Bravo"] call brmh_cmd_fnc_deleteStation;
	RETURNS: true
	ENVIRONMENT: Server
*/
params [["_callsign", "", [""]]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
{
	deleteVehicle _x;
} forEach units _group;
true
