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
