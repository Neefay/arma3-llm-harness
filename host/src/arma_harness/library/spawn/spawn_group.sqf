/*
	NAME: spawn_group
	DESCRIPTION: Spawn an infantry group of a side at a place, patrolling around it. With no type, the side's
		standard rifle squad (OPFOR OIA_InfSquad, BLUFOR BUS_InfSquad, independent HAF_InfSquad). A type is a
		CfgGroups class of that side, such as OIA_InfTeam or OI_reconTeam. Put them in buildings with garrison.
	PARAMETERS:
		0 - at (POSITION): where
		1 - side (SIDE, default "east"): whose side
		2 - type (STRING, default ""): the group's CfgGroups class
		3 - patrol (NUMBER, default 100): patrol radius in m; 0 to stay put
	RETURNS: [handle, men] (ARRAY)
	TARGET: server
	TAGS: spawn, enemy, squad, group, infantry, soldiers, patrol, create
	EXAMPLE: {"at": "player", "patrol": 0}
*/
params ["_at", "_side", "_type", "_patrol"];
if (_at isEqualTo []) exitWith {
	"ERROR: no such place: give [x, y], a grid such as 034 030, or a unit"
};
private _sideConfig = configFile >> "CfgGroups" >> (["Indep", "East", "West", "Civilian"] select (
	([independent, east, west, civilian] find _side) max 0));
if (_type isEqualTo "") then {
	_type = ["HAF_InfSquad", "OIA_InfSquad", "BUS_InfSquad", ""] select (([independent, east, west, civilian] find _side) max 0);
};
private _found = configNull;
{
	private _faction = _x;
	{
		if (isClass (_x >> _type)) exitWith {
			_found = _x >> _type;
		};
	} forEach ("true" configClasses _faction);
	if (isClass _found) exitWith {};
} forEach ("true" configClasses _sideConfig);
if (not isClass _found) exitWith {
	format ["ERROR: %1 has no group class %2", _side, _type]
};
private _group = [_at, _side, _found] call BIS_fnc_spawnGroup;
if (_patrol > 0) then {
	[_group, _at, _patrol] call BIS_fnc_taskPatrol;
};
private _handle = [[_group], format ["%1 %2", _side, _type]] call brmh_lib_fnc_keep;
[_handle, count units _group]
