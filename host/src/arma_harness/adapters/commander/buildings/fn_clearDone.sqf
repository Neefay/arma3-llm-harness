/*
	NAME: brmh_cmd_fnc_clearDone
	DESCRIPTION: A clearing leaves its building: checked if every position was stood on, and blocked, with how many, if
		not. Only the clearing machine calls it.
	PARAMETERS:
		0 - Clearing machine (HASHMAP object)
	USAGE:
		[_this] call brmh_cmd_fnc_clearDone;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
if ((_machine get "REACHED") >= (_machine get "OF")) then {
	(_machine get "CLEARED") pushBack (_machine get "CURRENT");
} else {
	(_machine get "BLOCKED") pushBack [_machine get "CURRENT", _machine get "REACHED", _machine get "OF"];
};
_machine set ["CURRENT", ""];
