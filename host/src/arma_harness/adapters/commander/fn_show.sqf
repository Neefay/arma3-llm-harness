/*
	NAME: brmh_cmd_fnc_show
	DESCRIPTION: A line of the radio for a human observer, in every player's chat. One-way, like brmh_cmd_fnc_mirror:
		nothing reads it back, so it can't help the commander.
	PARAMETERS:
		0 - Text (STRING)
	USAGE:
		["Alpha -> HQ: Moving, grid 040 041."] call brmh_cmd_fnc_show;
	RETURNS: true
	ENVIRONMENT: Server
*/
params [["_text", "", [""]]];
// A named event, not remoteExec, so no mission has to whitelist it: see @brmh's BRMH_fnc_commanderEvents.
["brmh_cmd_show", [_text]] call CBA_fnc_globalEvent;
true
