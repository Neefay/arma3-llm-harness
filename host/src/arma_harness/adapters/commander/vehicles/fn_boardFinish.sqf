/*
	NAME: brmh_cmd_fnc_boardFinish
	DESCRIPTION: Ends a boarding: those still on their way to a seat stop, and the squad's mount record says how it
		ended. Anyone already in his seat stays there.
	PARAMETERS:
		0 - Boarding machine (HASHMAP object)
		1 - How it ended: "on", "taken", "wrecked", "nobody", "unreachable" or "stopped" (STRING)
		2 - Names of those aboard (ARRAY of STRINGs)
	USAGE:
		[_machine, "stopped", []] call brmh_cmd_fnc_boardFinish;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine", "_word", "_names"];
{
	unassignVehicle (_x # 0);
	[_x # 0] orderGetIn false;
} forEach ([_machine] call brmh_cmd_fnc_boardWaiting);
(_machine get "GROUP") setVariable ["brmh_cmd_mount", [_machine get "KEY", _word, _machine get "SEAT", _names, _machine get "SPARE"]];
