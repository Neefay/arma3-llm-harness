/*
	NAME: brmh_cmd_fnc_stopMount
	DESCRIPTION: A new order stops a boarding partway, and says so: the mount record reads "stopped", and those still
		on their way are sent back. A getting-off under way is ended and its record goes, as does the last one's when
		nothing is under way.
	PARAMETERS:
		0 - Group (GROUP)
	USAGE:
		[_group] call brmh_cmd_fnc_stopMount;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
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
