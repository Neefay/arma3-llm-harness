// Every frame on the run: release the next bomb, a third of a second apart. A guided bomb goes inside the range it can
// glide to the grid from the run's height (spike_ace_bombs.py: from 2.5 km at 850 m, on the grid); an unguided one when
// it will land on the grid.
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
if (not _ready) exitWith {};
if ((_machine get "GUIDANCE") isEqualTo "GPS") then {
	ace_missileguidance_gps_mode = "pb";
	ace_missileguidance_gps_currentSettings = [_aim, -1, -1];
};
// The bomb leaves a frame or more later and is counted then, so the next isn't asked for before a third of a second.
_vehicle fireAtTarget [objNull, _machine get "WEAPON"];
_machine set ["NEXT", time + 0.33];
