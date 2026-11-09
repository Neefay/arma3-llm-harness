/*
	Two one-way feeds for a human observer. They write to the game's chat and map, and nothing reads them back,
	so they can't help the commander.
*/
params [["_text", "", [""]]];
// A named event, not remoteExec, so no mission has to whitelist it: see @brmh's BRMH_fnc_commanderEvents.
["brmh_cmd_show", [_text]] call CBA_fnc_globalEvent;
true
