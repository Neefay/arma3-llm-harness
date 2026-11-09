brmh_cmd_fireActive = brmh_cmd_fireActive select {
	_x call ["#STEP", []]
};
if (brmh_cmd_fireActive isEqualTo [] and {
	not isNil "brmh_cmd_firePfh"
}) then {
	[brmh_cmd_firePfh] call CBA_fnc_removePerFrameHandler;
	brmh_cmd_firePfh = nil;
};
