/*
	NAME: brmh_cmd_fnc_startPlacing
	DESCRIPTION: OCCUPY and CORDON: sends each free man to a spot, in turn, and starts the placing machine that holds
		them there. Spots are shared out round the squad, so with fewer spots than men some share one. Ends the
		squad's placing machine before.
	PARAMETERS:
		0 - Squad (GROUP)
		1 - Spots, one per man, such as a building's positions or a ring round a cordon (ARRAY of positions)
		2 - Where the men face once placed, or [] to leave them be (ARRAY)
	USAGE:
		[_group, _building buildingPos -1, []] call brmh_cmd_fnc_startPlacing;
		[_group, _ring, [3450, 3050, 0]] call brmh_cmd_fnc_startPlacing;
	RETURNS: The new length of brmh_cmd_builds (NUMBER)
	ENVIRONMENT: Server, unscheduled
*/
params ["_group", "_spots", "_watch"];
[_group, ["placing"]] call brmh_cmd_fnc_endMachines;
private _count = count _spots;
{
	if (_count > 0) then {
		_x doMove (_spots # (_forEachIndex mod _count));
	};
} forEach ([_group] call brmh_cmd_fnc_freeMen);
brmh_cmd_builds pushBack ([brmh_cmd_placingMachine, [["GROUP", _group], ["ORDER", _group getVariable ["brmh_cmd_order", ""]], ["SUBJECT", ""], ["WATCH", _watch]]] call brmh_cmd_fnc_newMachine);
