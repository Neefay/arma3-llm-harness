/*
	NAME: brmh_cmd_fnc_stepClearing
	DESCRIPTION: AI won't enter buildings to look for enemies it can't see, so soldiers are walked through every
		position in turn. A position only counts once someone has stood on it: AI can't get into some buildings at all
		(a cargo house's floor is up a step, and they stop 3 m outside), and a building nobody got into mustn't be
		reported as checked. Runs each step while the clearing is inside a building, and sets its BUSY to how many men
		are still on their way to a position.
	PARAMETERS:
		0 - Clearing machine (HASHMAP object)
	USAGE:
		[_this] call brmh_cmd_fnc_stepClearing;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
private _spots = _machine get "SPOTS";
private _busy = 0;
private _free = [_machine get "GROUP"] call brmh_cmd_fnc_freeMen;
// A man taken off to carry or treat, or down, gives back the position he was on his way to.
{
	private _held = _x getVariable "brmh_cmd_clearSpot";
	if (not isNil "_held" and {
		not (_x in _free)
	}) then {
		_spots pushBack _held;
		_x setVariable ["brmh_cmd_clearSpot", nil];
	};
} forEach units (_machine get "GROUP");
{
	private _soldier = _x;
	[_soldier] call brmh_cmd_fnc_noticeNearby;
	private _spot = _soldier getVariable "brmh_cmd_clearSpot";
	// On it, and on its floor: standing under a raised floor outside is close in a straight line.
	if (not isNil "_spot" and {
		(_soldier distance2D _spot) < 1.5
	} and {
		abs (((getPosATL _soldier) # 2) - (_spot # 2)) < 0.8
	}) then {
		_machine set ["REACHED", (_machine get "REACHED") + 1];
		_soldier setVariable ["brmh_cmd_clearSpot", nil];
	};
	// A position can be unreachable, so nobody waits for one for long: not past his deadline, and not once he's at
	// the building and has stopped getting closer, as when another squad's cordon stands in the doorway. Further off,
	// stopping is fighting or taking cover, and he still has his deadline. Men on a job aren't sent to one.
	if (not isNil "_spot") then {
		private _away = _soldier distance _spot;
		if (_away > 15 or {
			_away < (_soldier getVariable ["brmh_cmd_clearBest", 1e9]) - 1
		}) then {
			_soldier setVariable ["brmh_cmd_clearBest", _away];
			_soldier setVariable ["brmh_cmd_clearGain", time];
		};
	};
	if (time < (_soldier getVariable ["brmh_cmd_clearBy", 0]) and {
		not unitReady _soldier
	} and {
		(time - (_soldier getVariable ["brmh_cmd_clearGain", time])) < 20
	}) then {
		_busy = _busy + 1;
	} else {
		_soldier setVariable ["brmh_cmd_clearSpot", nil];
		if (_spots isNotEqualTo []) then {
			private _next = _spots deleteAt 0;
			_soldier doMove _next;
			_soldier setVariable ["brmh_cmd_clearSpot", _next];
			// 45 s once he's there: a squad given CLEAR from 500 m away has the walk to make first.
			_soldier setVariable ["brmh_cmd_clearBy", time + 45 + (_soldier distance _next) / 1.5];
			_soldier setVariable ["brmh_cmd_clearBest", _soldier distance _next];
			_soldier setVariable ["brmh_cmd_clearGain", time];
			_busy = _busy + 1;
		};
	};
} forEach _free;
_machine set ["BUSY", _busy];
