/*
	NAME: brmh_cmd_fnc_startTask
	DESCRIPTION: Hands a squad to one of CBA's group tasks, and starts the task machine that releases it from that task
		when the next order replaces it (brmh_cmd_taskMachine). Ends the squad's task machine before.
	PARAMETERS:
		0 - Squad (GROUP)
		1 - Task: "ATTACK", "DEFEND", "PATROL_AREA" or "SWEEP" (STRING)
		2 - Centre [x, y] (ARRAY)
		3 - Radius in metres (NUMBER)
	USAGE:
		[_group, "DEFEND", [3450, 3050], 100] call brmh_cmd_fnc_startTask;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_group", "_type", "_at", "_radius"];
private _centre = _at + [0];
[_group, ["task"]] call brmh_cmd_fnc_endMachines;
brmh_cmd_builds pushBack ([brmh_cmd_taskMachine, [["GROUP", _group], ["ORDER", _group getVariable ["brmh_cmd_order", ""]], ["SUBJECT", ""]]] call brmh_cmd_fnc_newMachine);
switch (_type) do {
	case "ATTACK": {
		[_group, _centre, _radius, true] call CBA_fnc_taskAttack;
	};
	case "DEFEND": {
		[_group, _centre, _radius, 3, false, 1] call CBA_fnc_taskDefend;
	};
	case "PATROL_AREA": {
		[_group, _centre, _radius, 4] call CBA_fnc_taskPatrol;
	};
	case "SWEEP": {
		[_group, [_centre, _radius, _radius, 0, false]] call CBA_fnc_taskSearchArea;
	};
};
