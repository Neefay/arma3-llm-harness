/*
	NAME: brmh_cmd_fnc_deleteStation
	DESCRIPTION: Removes a station's men from the game, for a scenario event, and for brmh_cmd_fnc_clearAll. The group
		itself stays. Operator action.
	PARAMETERS:
		0 - Callsign (STRING)
	USAGE:
		["Bravo"] call brmh_cmd_fnc_deleteStation;
	RETURNS: true
	ENVIRONMENT: Server, unscheduled
*/
params [["_callsign", "", [""]]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
// A man deleted in his seat can leave it blocked (Antistasi's postmortem loop uses deleteVehicleCrew for this).
{
	if (isNull objectParent _x) then {
		deleteVehicle _x;
	} else {
		objectParent _x deleteVehicleCrew _x;
	};
} forEach units _group;
true
