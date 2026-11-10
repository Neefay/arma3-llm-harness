brmh_cmd_carries = brmh_cmd_carries select {
	_x call ["#STEP", []]
};
if (brmh_cmd_carries isEqualTo [] and {
	not isNil "brmh_cmd_carryPfh"
}) then {
	[brmh_cmd_carryPfh] call CBA_fnc_removePerFrameHandler;
	brmh_cmd_carryPfh = nil;
};
