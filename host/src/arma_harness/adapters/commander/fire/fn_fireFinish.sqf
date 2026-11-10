/*
	NAME: brmh_cmd_fnc_fireFinish
	DESCRIPTION: Puts how a gun's fire mission ended on its record, which the packet carries for the host to word.
	PARAMETERS:
		0 - Fire machine (HASHMAP object)
		1 - How it ended: "done", "out", "gunner", "destroyed", "cantlay" or "stopped" (STRING)
	USAGE:
		[_this, "done"] call brmh_cmd_fnc_fireFinish;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine", "_state"];
(_machine get "MISSION") set ["state", _state];
