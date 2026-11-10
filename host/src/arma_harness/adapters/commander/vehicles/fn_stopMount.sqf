// A new order stops a boarding partway, and says so. With none under way, the last one's record goes.
params ["_group"];
private _machine = [_group] call brmh_cmd_fnc_boarding;
if (isNil "_machine") exitWith {
	_group setVariable ["brmh_cmd_mount", []];
};
if ((_machine get "STATE") isEqualTo "going") then {
	[_machine, "stopped", []] call brmh_cmd_fnc_boardFinish;
	((_group getVariable ["brmh_cmd_mount", []]) resize 4);
} else {
	_group setVariable ["brmh_cmd_mount", []];
};
_machine call ["#END", []];
