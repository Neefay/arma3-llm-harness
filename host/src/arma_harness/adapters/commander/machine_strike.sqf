// A strike: bombs on a grid, whatever is seen there. The pilot flies the run on engine waypoints, from a point 5 km out
// on the heading given (or straight from where he is), and the release is timed by script, each frame, for the grid.
// With ACE the bombs are ACE's own and guided: a laser shone straight down on the grid, or the GPS aim point.
// Without ACE they fall where the release puts them (docs/COMMANDER_CAS.md).
brmh_cmd_strikeMachine = [
	["KIND", "strike"],
	["INITIAL", "inbound"],
	["ALWAYS", [
		[{
			not alive (_this get "VEHICLE") or {
				not ([driver (_this get "VEHICLE")] call brmh_cmd_fnc_able)
			}
		}, {}, "", "lost"]
	]],
	["STATES", [
		["inbound", [
			["ON", [
				[{
					(_this get "DIRECT") or {
						((_this get "VEHICLE") distance2D (_this get "IP")) < 1000
					}
				}, {
					[_this] call brmh_cmd_fnc_strikeRun;
					_this get "GRID"
				}, "run", "in hot"]
			]],
			["DEADLINE", [600, {
				_this get "GRID"
			}, "", "no release"]]
		]],
		["run", [
			["ON", [
				[{
					private _released = [_this] call brmh_cmd_fnc_strikeReleased;
					_released >= (_this get "BOMBS") or {
						_released > 0 and {
							[_this] call brmh_cmd_fnc_strikePassed
						}
					}
				}, {
					[[_this] call brmh_cmd_fnc_strikeReleased] call brmh_cmd_fnc_bombWords
				}, "away", "away"],
				[{
					(_this get "PASSES") isEqualTo 0 and {
						[_this] call brmh_cmd_fnc_strikePassed
					}
				}, {
					[_this] call brmh_cmd_fnc_strikeAround;
				}, "inbound", "going around"],
				[{
					[_this] call brmh_cmd_fnc_strikePassed
				}, {
					_this get "GRID"
				}, "", "no release"]
			]],
			["DEADLINE", [240, {
				_this get "GRID"
			}, "", "no release"]]
		]],
		["away", [
			["DEADLINE", [10, {}, "", "off target"]]
		]]
	]],
	["RELEASE", {
		private _group = _this get "GROUP";
		private _vehicle = _this get "VEHICLE";
		[_this getOrDefault ["PFH", -1]] call CBA_fnc_removePerFrameHandler;
		// The laser stays on until the last bomb has had time to land.
		private _laser = _this getOrDefault ["LASER", []];
		if (_laser isNotEqualTo []) then {
			[{
				params ["_uuid", "_emitter"];
				[_uuid] call ace_laser_fnc_laserOff;
				deleteVehicle _emitter;
			}, _laser, 60] call CBA_fnc_waitAndExecute;
		};
		if (alive _vehicle) then {
			_vehicle flyInHeight (_vehicle getVariable ["brmh_cmd_flyHeight", 300]);
			_group setBehaviour "AWARE";
			[_group, _group getVariable ["brmh_cmd_hold", getPosATL _vehicle]] call brmh_cmd_fnc_holdAir;
		};
	}]
];
