params ["_group", "_spots", "_watch"];
[_group, ["placing"]] call brmh_cmd_fnc_endMachines;
private _count = count _spots;
{
	if (_count > 0) then {
		_x doMove (_spots # (_forEachIndex mod _count));
	};
} forEach ([_group] call brmh_cmd_fnc_freeMen);
brmh_cmd_builds pushBack ([brmh_cmd_placingMachine, [["GROUP", _group], ["ORDER", _group getVariable ["brmh_cmd_order", ""]], ["SUBJECT", ""], ["WATCH", _watch]]] call brmh_cmd_fnc_newMachine);
