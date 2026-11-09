/*
	NAME: BRMH_fnc_commanderEvents
	DESCRIPTION: Commander mode's broadcasts, as named events rather than remoteExec, so no mission has to whitelist
		anything for it: a pose (switchMove) that every machine has to see, and a line of the observers' chat feed.
	PARAMETERS: None
	USAGE:
		Runs automatically (CfgFunctions postInit). The commander raises them:
		["brmh_cmd_pose", [_unit, "UnconsciousReviveDefault"]] call CBA_fnc_globalEvent;
		["brmh_cmd_show", ["Alpha -> HQ: Moving."]] call CBA_fnc_globalEvent;
	RETURNS: Nothing
	ENVIRONMENT: Every machine, postInit, unscheduled
*/

// switchMove only changes the machine it runs on: on the server alone, a carried man stayed on the ground for anyone
// watching.
["brmh_cmd_pose", {
	params [["_unit", objNull, [objNull]], ["_animation", "", [""]]];
	if (not isNull _unit) then {
		_unit switchMove _animation;
	};
}] call CBA_fnc_addEventHandler;

["brmh_cmd_show", {
	params [["_text", "", [""]]];
	if (hasInterface) then {
		systemChat _text;
	};
}] call CBA_fnc_addEventHandler;
