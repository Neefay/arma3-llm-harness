/*
	NAME: brmh_cmd_fnc_strikeRelease
	DESCRIPTION: Every frame on the run: releases the next bomb when it's time. A guided bomb goes inside the range it
		can glide to the grid from the run's height (spike_ace_bombs.py: from 2.5 km at 850 m, on the grid), between
		600 m and BRMH_CMD_GUIDED_RELEASE_M out and lined up within 15°; an unguided one when brmh_cmd_fnc_bombImpact
		puts it on the grid. After the first, the rest follow as a stick, a third of a second apart. A GPS bomb reads
		its aim point from ACE's GPS settings when it's fired, so they're set just before.
	PARAMETERS:
		0 - Strike machine (HASHMAP object)
	USAGE:
		[_machine] call brmh_cmd_fnc_strikeRelease;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled. From the per-frame handler brmh_cmd_fnc_strikeRun adds, in the "run" state only.
*/
params ["_machine"];
if (([_machine] call brmh_cmd_fnc_strikeReleased) >= (_machine get "BOMBS") or {
	time < (_machine get "NEXT")
}) exitWith {};
private _vehicle = _machine get "VEHICLE";
private _aim = _machine get "AIM";
private _velocity = velocity _vehicle;
private _flat = [_velocity # 0, _velocity # 1, 0];
if ((vectorMagnitude _flat) < 20) exitWith {};
private _ready = switch (true) do {
	// After the first, the rest follow as a stick.
	case (([_machine] call brmh_cmd_fnc_strikeReleased) > 0): {
		true
	};
	case ((_machine get "GUIDANCE") isNotEqualTo ""): {
		private _distance = _vehicle distance2D _aim;
		_distance <= BRMH_CMD_GUIDED_RELEASE_M and {
			_distance > 600
		} and {
			([_vehicle, _aim] call brmh_cmd_fnc_offTrack) < 15
		}
	};
	// From further out a bomb can't reach (its throw is under 2 km), so its fall isn't worked out every frame.
	case ((_vehicle distance2D _aim) > 3500): {
		false
	};
	default {
		private _along = vectorNormalized _flat;
		private _miss = _aim vectorDiff ([getPosASL _vehicle, _velocity, _machine get "SIDE"] call brmh_cmd_fnc_bombImpact);
		private _short = _miss vectorDotProduct _along;
		_short <= 0 and {
			_short > -100
		} and {
			abs ((_miss # 0) * (_along # 1) - (_miss # 1) * (_along # 0)) < 80
		}
	};
};
// ACE copies its GPS aim point when the bomb's Fired runs, a frame or more on, so two strikes releasing together would
// share one aim. The second waits half a second.
if (not _ready or {
	(_machine get "GUIDANCE") isEqualTo "GPS" and {
		time < brmh_cmd_gpsBusyUntil
	}
}) exitWith {};
if ((_machine get "GUIDANCE") isEqualTo "GPS") then {
	ace_missileguidance_gps_mode = "pb";
	ace_missileguidance_gps_currentSettings = [_aim, -1, -1];
	brmh_cmd_gpsBusyUntil = time + 0.5;
};
// The bomb leaves a frame or more later and is counted then, so the next isn't asked for before a third of a second.
_vehicle fireAtTarget [objNull, _machine get "WEAPON"];
_machine set ["NEXT", time + 0.33];
