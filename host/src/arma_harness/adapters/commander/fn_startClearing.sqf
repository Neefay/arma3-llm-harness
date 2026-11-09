params ["_group", "_buildings"];
[_group, ["clearing"]] call brmh_cmd_fnc_endMachines;
{
	_x setVariable ["brmh_cmd_clearBy", 0];
	_x setVariable ["brmh_cmd_clearSpot", nil];
} forEach units _group;
brmh_cmd_builds pushBack ([brmh_cmd_clearingMachine, [["GROUP", _group], ["ORDER", _group getVariable ["brmh_cmd_order", ""]], ["SUBJECT", ""], ["QUEUE", +_buildings], ["SPOTS", []], ["CURRENT", ""], ["REACHED", 0], ["OF", 0], ["BUSY", 0], ["CLEARED", []], ["RUINED", []], ["BLOCKED", []]]] call brmh_cmd_fnc_newMachine);
