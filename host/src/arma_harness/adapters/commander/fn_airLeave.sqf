/*
	NAME: brmh_cmd_fnc_airLeave
	DESCRIPTION: An aircraft at the end of its time on station flies off, 5 km out from the middle of the map, and circles
		there. It isn't deleted, so its crew don't count as lost. Called by the host, which refuses it orders from then on.
	PARAMETERS:
		0 - Callsign (STRING)
	USAGE:
		["Hawg"] call brmh_cmd_fnc_airLeave;
	RETURNS: Nothing
	ENVIRONMENT: Server
*/
params [["_callsign", "", [""]]];
private _group = brmh_cmd_stations getOrDefault [_callsign, grpNull];
if (isNull _group) exitWith {};
{
	if ((_x get "GROUP") isEqualTo _group) then {
		_x call ["#END", ["bingo"]];
	};
} forEach brmh_cmd_builds;
private _vehicle = vehicle leader _group;
private _away = _vehicle getPos [5000, [worldSize / 2, worldSize / 2] getDir _vehicle];
[_group, _away] call brmh_cmd_fnc_holdAir;
_group setCombatMode "BLUE";
