// A medic's job, one casualty: he goes to him, then works on him until he's up. Its words are the radio's. States:
// going and working. Made by brmh_cmd_fnc_stepTreats, and stepped every 2 s in brmh_cmd_builds by stepBuilds.
brmh_cmd_treatMachine = [
	["KIND", "treat"],
	["INITIAL", "going"],
	["ALWAYS", [
		[{
			not ([_this get "MEDIC"] call brmh_cmd_fnc_able)
		}, {
			// Back in the queue, for another medic.
			((_this get "TREAT") get "QUEUE") pushBack (_this get "SUBJECT");
		}, "", "medic down"],
		[{
			not alive (_this get "SUBJECT")
		}, {}, "", "he died"]
	]],
	["STATES", [
		["going", [
			["EVERY", {
				if (((_this get "MEDIC") distance2D (_this get "LAST")) >= 1) then {
					_this set ["LAST", getPosATL (_this get "MEDIC")];
					_this set ["MOVED", time];
				};
			}],
			["ON", [
				[{
					[_this] call brmh_cmd_fnc_treatArrived
				}, {
					[_this] call brmh_cmd_fnc_treatStart
				}, "working", "treating"],
				// As with a carry: as close as he can get. He works for a while, and the man is then with him.
				[{
					not ([_this] call brmh_cmd_fnc_treatAboard) and {
						[_this] call brmh_cmd_fnc_treatReady
					} and {
						((_this get "MEDIC") distance (_this get "SUBJECT")) <= 35
					}
				}, {
					[_this] call brmh_cmd_fnc_treatPull;
					[_this] call brmh_cmd_fnc_treatStart
				}, "working", "treating"],
				[{
					[_this] call brmh_cmd_fnc_treatStuck and {
						[_this] call brmh_cmd_fnc_treatTriesLeft
					}
				}, {
					[_this] call brmh_cmd_fnc_treatApproach;
				}, "going", ""],
				// The owner's way, as a last resort: he was close, and now the man's with him.
				[{
					[_this] call brmh_cmd_fnc_treatStuck and {
						not ([_this] call brmh_cmd_fnc_treatAboard)
					} and {
						((_this get "MEDIC") distance (_this get "SUBJECT")) <= 60
					}
				}, {
					[_this] call brmh_cmd_fnc_treatPull;
					[_this] call brmh_cmd_fnc_treatStart
				}, "working", "treating"],
				[{
					[_this] call brmh_cmd_fnc_treatStuck
				}, {}, "", "can't reach"]
			]],
			["DEADLINE", [600, {}, "", "can't reach"]]
		]],
		["working", [
			["EVERY", {
				[_this] call brmh_cmd_fnc_treatWork
			}],
			["ON", [
				[{
					[_this get "SUBJECT"] call brmh_cmd_fnc_able
				}, {}, "", "up"],
				[{
					(time - (_this get "SINCE")) >= (_this get "NEED")
				}, {
					[_this] call brmh_cmd_fnc_treatDone
				}, "", "up"]
			]],
			["DEADLINE", [{
				(_this get "NEED") + 5
			}, {
				[_this] call brmh_cmd_fnc_treatDone
			}, "", "up"]]
		]]
	]],
	["RELEASE", {
		[_this] call brmh_cmd_fnc_treatRelease
	}]
];
