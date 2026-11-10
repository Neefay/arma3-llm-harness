// A gun's fire mission, one per gun, stepped every half second while any is running. Its state is the mission
// record's, which the packet carries for the host to word: firing or holding while it lasts, then how it ended.
brmh_cmd_fireMachine = [
	["KIND", "fire"],
	["SAYS", false],
	["INITIAL", "firing"],
	["ALWAYS", [
		[{
			not alive (_this get "GUN")
		}, {
			[_this, "destroyed"] call brmh_cmd_fnc_fireFinish
		}, "", ""],
		// Down under ACE, he's alive and still in the seat, and the gun just doesn't fire.
		[{
			private _crew = gunner (_this get "GUN");
			isNull _crew or {
				not ([_crew] call brmh_cmd_fnc_able)
			}
		}, {
			[_this, "gunner"] call brmh_cmd_fnc_fireFinish
		}, "", ""],
		[{
			((_this get "MISSION") getOrDefault ["fired", 0]) >= ((_this get "MISSION") get "want")
		}, {
			[_this, "done"] call brmh_cmd_fnc_fireFinish
		}, "", ""],
		// That order's rounds are away. If that's all this type has, it's out; if not, the next order goes.
		[{
			[_this] call brmh_cmd_fnc_fireReady and {
				[_this] call brmh_cmd_fnc_fireAway
			} and {
				[_this] call brmh_cmd_fnc_fireOut
			}
		}, {
			[_this, "out"] call brmh_cmd_fnc_fireFinish
		}, "", ""],
		[{
			[_this] call brmh_cmd_fnc_fireReady and {
				[_this] call brmh_cmd_fnc_fireAway
			}
		}, {
			[_this get "MISSION"] call brmh_cmd_fnc_fireChunk;
			(_this get "MISSION") set ["state", "firing"];
		}, "firing", ""],
		// The engine says it can reach, and it doesn't fire. A Scorcher did this at 2,000 m, every time.
		[{
			[_this] call brmh_cmd_fnc_fireReady and {
				not ([_this] call brmh_cmd_fnc_fireAway)
			} and {
				([_this] call brmh_cmd_fnc_sinceShot) >= 15
			}
		}, {
			[_this, "cantlay"] call brmh_cmd_fnc_fireFinish
		}, "", ""]
	]],
	["STATES", [
		["firing", [
			["ON", [
				[{
					([_this] call brmh_cmd_fnc_sinceShot) >= 10 and {
						not ([_this] call brmh_cmd_fnc_fireAway)
					} and {
						(currentCommand gunner (_this get "GUN")) isEqualTo "FIRE AT POSITION"
					}
				}, {
					(_this get "MISSION") set ["state", "holding"];
				}, "holding", ""]
			]],
			// Each order to the gun is watched above; this is only a backstop for a mission that never ends.
			["DEADLINE", [600, {
				[_this, "cantlay"] call brmh_cmd_fnc_fireFinish
			}, "", ""]]
		]],
		["holding", [
			["ON", [
				[{
					((_this get "MISSION") getOrDefault ["lastShot", -1]) > (_this get "SINCE")
				}, {
					(_this get "MISSION") set ["state", "firing"];
				}, "firing", ""]
			]],
			["DEADLINE", [600, {
				[_this, "cantlay"] call brmh_cmd_fnc_fireFinish
			}, "", ""]]
		]]
	]]
];
