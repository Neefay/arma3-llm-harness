/*
	NAME: brmh_cmd_fnc_stepCarries
	DESCRIPTION: Steps every carry and drops those that have ended. With none left, it removes its own per-frame
		handler, which brmh_cmd_fnc_startCarry adds again for the next one.
	PARAMETERS: None
	USAGE:
		call brmh_cmd_fnc_stepCarries; // every 0.5 s, from the handler brmh_cmd_fnc_startCarry adds
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled (a CBA per-frame handler)
*/
brmh_cmd_carries = brmh_cmd_carries select {
	_x call ["#STEP", []]
};
if (brmh_cmd_carries isEqualTo [] and {
	not isNil "brmh_cmd_carryPfh"
}) then {
	[brmh_cmd_carryPfh] call CBA_fnc_removePerFrameHandler;
	brmh_cmd_carryPfh = nil;
};
