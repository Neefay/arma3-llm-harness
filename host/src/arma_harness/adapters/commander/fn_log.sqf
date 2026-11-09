/*
	NAME: brmh_cmd_fnc_log
	DESCRIPTION: The game side's own diagnostics, written to the RPT as "[Commander:Source] Level: message" when at or
		above BRMH_CMD_LOG_LEVEL. With BRMH_CMD_LOG_SCREEN set, warnings and errors are also shown in the observers'
		chat. For whoever runs the harness: none of it reaches the host or the commander.
	PARAMETERS:
		0 - Source, the part of the game side writing (STRING)
		1 - Level: "ERROR", "WARNING", "INFO" or "DEBUG" (STRING)
		2 - Message, a format string (STRING)
		3 - (OPTIONAL) Its arguments (ARRAY) - Default: []
	USAGE:
		["Machines", "ERROR", "machine %1: %2", ["carry", "going waits with no deadline"]] call brmh_cmd_fnc_log;
		["Spawn", "WARNING", "no such vehicle class %1", [_class]] call brmh_cmd_fnc_log;
	RETURNS: Nothing
	ENVIRONMENT: Server
*/
params [["_source", "", [""]], ["_level", "INFO", [""]], ["_message", "", [""]], ["_args", [], [[]]]];
private _levels = ["DEBUG", "INFO", "WARNING", "ERROR"];
private _rank = (_levels find toUpperANSI _level) max 0;
if (_rank < ((_levels find BRMH_CMD_LOG_LEVEL) max 0)) exitWith {};
private _line = format ["[Commander:%1] %2: %3", _source, ["Debug", "Info", "Warning", "Error"] # _rank, format ([_message] + _args)];
diag_log text _line;
if (BRMH_CMD_LOG_SCREEN and {
	_rank >= 2
}) then {
	[_line] call brmh_cmd_fnc_show;
};
