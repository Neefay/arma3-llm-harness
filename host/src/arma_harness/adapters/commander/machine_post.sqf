// The aid post: a medic walks to the place, then builds. Its states are the words the radio uses for them.
brmh_cmd_postMachine = [
	["KIND", "post"],
	["INITIAL", "going"],
	["ALWAYS", [
		[{
			not ([_this get "MEDIC"] call brmh_cmd_fnc_able)
		}, {}, "", "medic down"]
	]],
	["STATES", [
		["going", [
			["ON", [
				[{
					private _away = (_this get "MEDIC") distance2D (_this get "AT");
					_away <= 8 or {
						[_this] call brmh_cmd_fnc_postStopped and {
							_away <= 40
						}
					}
				}, {
					private _medic = _this get "MEDIC";
					doStop _medic;
					_medic disableAI "ANIM";
					[_medic, "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
				}, "building", "building"],
				[{
					[_this] call brmh_cmd_fnc_postStopped
				}, {}, "", "can't reach"]
			]],
			// It used to wait for good on a medic who never stopped walking and never got there.
			["DEADLINE", [300, {}, "", "can't reach"]]
		]],
		["building", [
			["DEADLINE", [{
				brmh_cmd_careTimes get "build_s"
			}, {
				[_this] call brmh_cmd_fnc_postBuilt
			}, "", "up"]]
		]]
	]],
	["RELEASE", {
		private _medic = _this get "MEDIC";
		_medic setVariable ["brmh_cmd_busy", nil];
		if (alive _medic) then {
			_medic enableAI "ANIM";
		};
		if ([_medic] call brmh_cmd_fnc_able) then {
			[_medic, "AmovPknlMstpSrasWrflDnon"] call brmh_cmd_fnc_carryPose;
			_medic doFollow leader group _medic;
		};
	}]
];
