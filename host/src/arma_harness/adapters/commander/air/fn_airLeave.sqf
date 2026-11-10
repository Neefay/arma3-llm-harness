/*
	NAME: brmh_cmd_fnc_airLeave
	DESCRIPTION: An aircraft at the end of its time on station calls off its strike or sortie ("bingo"), flies 5 km on,
		straight away from the middle of the map, and circles there holding fire. It isn't deleted, so its crew don't
		count as lost. Called by the host, which says the bingo call itself and refuses it orders from then on.
	PARAMETERS:
		0 - Callsign (STRING)
	USAGE:
		["Hawg"] call brmh_cmd_fnc_airLeave;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
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
