// MOUNT and DISMOUNT: the squad's men going to their seats, or getting off. Its state reaches the host in the packet's
// "mount" record, [vehicle id, state, seat, names, spare men], which keeps how it ended until the next one. A boarding
// that can't start at all (no vehicle, seat or man) is a record and no machine.
brmh_cmd_boardingMachine = [
	["KIND", "boarding"],
	["SAYS", false],
	["INITIAL", "going"],
	["STATES", [
		["going", [
			["EVERY", {
				{
					if (vehicle (_x # 0) isEqualTo (_this get "VEHICLE")) then {
						[_x # 0, _this get "VEHICLE"] call brmh_cmd_fnc_onSeat;
					};
				} forEach (_this get "LIST");
			}],
			["ON", [
				[{
					not alive (_this get "VEHICLE")
				}, {
					[_this, "wrecked", []] call brmh_cmd_fnc_boardFinish
				}, "", ""],
				[{
					([_this] call brmh_cmd_fnc_boardWaiting) isEqualTo [] and {
						([_this] call brmh_cmd_fnc_boardOn) isEqualTo []
					}
				}, {
					[_this, "nobody", []] call brmh_cmd_fnc_boardFinish
				}, "", ""],
				[{
					([_this] call brmh_cmd_fnc_boardWaiting) isEqualTo []
				}, {
					[_this, "on", ([_this] call brmh_cmd_fnc_boardOn) apply {
						name _x
					}] call brmh_cmd_fnc_boardFinish
				}, "", ""],
				// The engine has a man wait beside a seat someone else has taken, with no error.
				[{
					[_this] call brmh_cmd_fnc_boardTaken
				}, {
					[_this, "taken", ([_this] call brmh_cmd_fnc_boardOn) apply {
						name _x
					}] call brmh_cmd_fnc_boardFinish
				}, "", ""]
			]],
			["DEADLINE", [{
				_this get "WITHIN"
			}, {
				[_this, "unreachable", ([_this] call brmh_cmd_fnc_boardOn) apply {
					name _x
				}] call brmh_cmd_fnc_boardFinish
			}, "", ""]]
		]],
		["going off", [
			["ON", [
				[{
					([_this] call brmh_cmd_fnc_stillAboard) isEqualTo []
				}, {
					((_this get "GROUP") getVariable ["brmh_cmd_mount", []]) set [1, "off"];
				}, "", ""]
			]],
			// Something's keeping them in. Waiting on it for good would leave a chained order hanging, with nobody
			// saying why.
			["DEADLINE", [30, {
				private _status = (_this get "GROUP") getVariable ["brmh_cmd_mount", []];
				_status set [1, "stuck"];
				_status set [3, ([_this] call brmh_cmd_fnc_stillAboard) apply {
					name _x
				}];
			}, "", ""]]
		]]
	]]
];
