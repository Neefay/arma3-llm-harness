/*
	NAME: brmh_cmd_fnc_stepFire
	DESCRIPTION: Steps every running fire machine and drops those that have ended. It runs from its own per-frame
		handler, every half second, which it removes once none are left; brmh_cmd_fnc_startFire adds it again.
	PARAMETERS: None
	USAGE:
		call brmh_cmd_fnc_stepFire;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled (a CBA per-frame handler)
*/
brmh_cmd_fireActive = brmh_cmd_fireActive select {
	_x call ["#STEP", []]
};
if (brmh_cmd_fireActive isEqualTo [] and {
	not isNil "brmh_cmd_firePfh"
}) then {
	[brmh_cmd_firePfh] call CBA_fnc_removePerFrameHandler;
	brmh_cmd_firePfh = nil;
};
