// The monitor: every 2 s, each squad's report, and the machines' steps.
brmh_cmd_pfh = [{
	call brmh_cmd_fnc_step;
}, 2] call CBA_fnc_addPerFrameHandler;
true
