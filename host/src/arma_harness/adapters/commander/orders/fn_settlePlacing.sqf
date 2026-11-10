/*
	NAME: brmh_cmd_fnc_settlePlacing
	DESCRIPTION: An OCCUPY or CORDON settles: the squad's free men stop where they are, and a cordon's face its
		centre.
	PARAMETERS:
		0 - The squad's placing machine (HASHMAP object)
	USAGE:
		[_machine] call brmh_cmd_fnc_settlePlacing;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
private _soldiers = [_machine get "GROUP"] call brmh_cmd_fnc_freeMen;
doStop _soldiers;
if ((_machine get "WATCH") isNotEqualTo []) then {
	_soldiers doWatch (_machine get "WATCH");
};
