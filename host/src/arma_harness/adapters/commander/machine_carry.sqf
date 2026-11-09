// A carry: the bearer goes to the casualty, lifts him and carries him to a place or a vehicle. Stepped every half
// second by brmh_cmd_fnc_stepCarries. Its words are the radio's, with the casualty as their subject.
brmh_cmd_carryMachine = [
	["KIND", "carry"],
	["INITIAL", "going"],
	["ALWAYS", [
		[{
			private _medic = _this get "MEDIC";
			not alive _medic or {
				lifeState _medic isEqualTo "INCAPACITATED"
			}
		}, {}, "", "medic down"],
		[{
			not alive (_this get "SUBJECT")
		}, {}, "", "he died"],
		[{
			lifeState (_this get "SUBJECT") isNotEqualTo "INCAPACITATED"
		}, {}, "", "he woke"]
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
				// A house position can stop him a few metres short, through a wall or not. He snaps the man to him when
				// he lifts.
				[{
					private _away = (_this get "MEDIC") distance (_this get "SUBJECT");
					_away <= 2.5 or {
						_away <= 8 and {
							[_this] call brmh_cmd_fnc_carryReady or {
								(time - (_this get "MOVED")) >= 8
							}
						}
					}
				}, {
					[_this] call brmh_cmd_fnc_carryStartLift
				}, "lifting", ""],
				// As close as he can get. The owner's way: he works for a while, and the man is then with him.
				[{
					[_this] call brmh_cmd_fnc_carryReady and {
						((_this get "MEDIC") distance (_this get "SUBJECT")) <= 35
					}
				}, {
					[_this get "MEDIC", "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
				}, "fetching", ""],
				[{
					[_this] call brmh_cmd_fnc_carryStuck and {
						[_this] call brmh_cmd_fnc_carryTriesLeft
					}
				}, {
					[_this] call brmh_cmd_fnc_carryApproach;
				}, "going", ""],
				[{
					[_this] call brmh_cmd_fnc_carryStuck and {
						((_this get "MEDIC") distance (_this get "SUBJECT")) <= 60
					}
				}, {
					[_this get "MEDIC", "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
				}, "fetching", ""],
				[{
					[_this] call brmh_cmd_fnc_carryStuck
				}, {}, "", "can't reach him"]
			]],
			["DEADLINE", [600, {}, "", "can't reach him"]]
		]],
		["fetching", [
			["DEADLINE", [8, {
				private _medic = _this get "MEDIC";
				private _casualty = _this get "SUBJECT";
				_casualty setPosATL (_medic getPos [1.2, getDir _medic]);
				[_casualty, "UnconsciousReviveDefault"] call brmh_cmd_fnc_carryPose;
				[_medic, "AmovPercMstpSrasWrflDnon"] call brmh_cmd_fnc_carryPose;
				[_this] call brmh_cmd_fnc_carryStartLift
			}, "lifting", ""]]
		]],
		["lifting", [
			["DEADLINE", [9, {
				[_this] call brmh_cmd_fnc_carryLift
			}, "carrying", "carrying"]]
		]],
		["carrying", [
			["EVERY", {
				private _dummy = _this get "DUMMY";
				if ((_dummy distance2D (_this get "LAST")) >= 1) then {
					_this set ["LAST", getPosATL _dummy];
					_this set ["MOVED", time];
				};
			}],
			["ON", [
				// A vehicle's own bulk stops the dummy short of its middle.
				[{
					(_this get "TO") isEqualType objNull and {
						([_this] call brmh_cmd_fnc_carryLeft) <= 8
					}
				}, {
					[_this, "carried"] call brmh_cmd_fnc_carryLoad
				}, "loading", ""],
				[{
					([_this] call brmh_cmd_fnc_carryLeft) <= 5
				}, {
					[_this] call brmh_cmd_fnc_carryRelease
				}, "", "carried"],
				// Not far: the owner's way, of working on him a while and then putting him there.
				[{
					(time - (_this get "MOVED")) >= 8 and {
						([_this] call brmh_cmd_fnc_carryLeft) <= 60
					}
				}, {
					[_this] call brmh_cmd_fnc_carryRelease;
					(_this get "MEDIC") disableAI "ANIM";
					[_this get "MEDIC", "AinvPknlMstpSlayWrflDnon_medicOther"] call brmh_cmd_fnc_carryPose;
				}, "working", ""],
				[{
					(time - (_this get "MOVED")) >= 8
				}, {}, "", "stuck"]
			]],
			// The dummy's own stall above does the work; a carry to a far place is slow, about 100 m a minute.
			["DEADLINE", [1800, {}, "", "stuck"]]
		]],
		["working", [
			["ON", [
				[{
					(time - (_this get "SINCE")) >= 8 and {
						(_this get "TO") isEqualType objNull
					}
				}, {
					[_this, "placed"] call brmh_cmd_fnc_carryLoad
				}, "loading", ""],
				[{
					(time - (_this get "SINCE")) >= 8
				}, {
					(_this get "SUBJECT") setPosATL (_this get "TO");
				}, "", "placed"]
			]],
			["DEADLINE", [10, {}, "", "placed"]]
		]],
		["loading", [
			["ON", [
				[{
					vehicle (_this get "SUBJECT") isEqualTo (_this get "TO") and {
						(_this get "HOW") isEqualTo "placed"
					}
				}, {}, "", "loaded directly"],
				[{
					vehicle (_this get "SUBJECT") isEqualTo (_this get "TO")
				}, {}, "", "loaded"]
			]],
			["DEADLINE", [5, {}, "", "couldn't load him"]]
		]]
	]],
	// However it ends: he's let go of, and the bearer's free again.
	["RELEASE", {
		private _medic = _this get "MEDIC";
		[_this] call brmh_cmd_fnc_carryRelease;
		if ([_medic] call brmh_cmd_fnc_able) then {
			_medic doFollow leader group _medic;
		};
		_medic setVariable ["brmh_cmd_busy", nil];
		(_this get "SUBJECT") setVariable ["brmh_cmd_handled", nil];
	}]
];
