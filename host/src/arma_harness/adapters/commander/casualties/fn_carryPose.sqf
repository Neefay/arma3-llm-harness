/*
	NAME: brmh_cmd_fnc_carryPose
	DESCRIPTION: Puts a man straight into an animation (switchMove) on every machine. switchMove only changes the
		machine it runs on. On the server alone, the body stayed on the ground for anyone watching, and the server's own
		state said all was well. @brmh's BRMH_fnc_commanderEvents handles the event, and plays it on every machine.
	PARAMETERS:
		0 - Man (OBJECT)
		1 - Animation (STRING)
	USAGE:
		[_casualty, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. Raised as a CBA global event, handled on every machine
*/
params ["_unit", "_animation"];
["brmh_cmd_pose", [_unit, _animation]] call CBA_fnc_globalEvent;
