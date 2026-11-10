// Past the grid without releasing: it's behind him, or he's over it.
params ["_machine"];
private _vehicle = _machine get "VEHICLE";
private _aim = _machine get "AIM";
private _distance = _vehicle distance2D _aim;
_distance < 300 or {
	_distance < 3000 and {
		([_vehicle, _aim] call brmh_cmd_fnc_offTrack) > 90
	}
}
