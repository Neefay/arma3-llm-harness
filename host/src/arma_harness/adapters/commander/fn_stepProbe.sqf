{
	private _walker = _x;
	private _man = _walker get "MAN";
	private _spot = _walker get "SPOT";
	if (time >= (_walker get "START") and {
		not ("SENT" in _walker)
	}) then {
		_man doMove _spot;
		_walker set ["SENT", true];
	};
	if ("SENT" in _walker) then {
		private _away = _man distance _spot;
		if (_away < (_walker get "BEST") - 0.5) then {
			_walker set ["BEST", _away];
			_walker set ["GAIN", time];
		};
		// The same test as clearing's: on the position, and on its floor.
		if ((_man distance2D _spot) < 1.5 and {
			abs (((getPosATL _man) # 2) - (_spot # 2)) < 0.8
		}) then {
			_walker set ["RESULT", true];
		} else {
			if (not alive _man or {
				(time - (_walker get "GAIN")) > 20
			} or {
				(time - (_walker get "START")) > 120
			}) then {
				_walker set ["RESULT", false];
			};
		};
	};
} forEach (brmh_cmd_probeWalkers select {
	not ("RESULT" in _x)
});
if ((brmh_cmd_probeWalkers findIf {
	not ("RESULT" in _x)
}) < 0) then {
	// Only buildings with two or more reached positions. A man alone in a one-room building can't be fought for: a
	// clearer stops at the door, neither can see the other, and he outlasts the battle (Camp Maxwell, B5).
	private _reached = brmh_cmd_probeWalkers select {
		_x get "RESULT"
	};
	brmh_cmd_probe = [true, (_reached select {
		private _house = _x get "HOUSE";
		({
			(_x get "HOUSE") isEqualTo _house
		} count _reached) >= 2
	}) apply {
		_x get "SPOT"
	}];
	{
		deleteVehicle (_x get "MAN");
	} forEach brmh_cmd_probeWalkers;
	brmh_cmd_probeWalkers = [];
	[brmh_cmd_probePfh] call CBA_fnc_removePerFrameHandler;
	brmh_cmd_probePfh = nil;
};
