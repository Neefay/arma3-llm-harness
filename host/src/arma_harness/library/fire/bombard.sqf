/*
	NAME: bombard
	DESCRIPTION: An artillery barrage on a place: shells falling at random within a radius, one every 0.4 s.
		Refused, without firing, if any player or a unit in a player's squad is closer than the safety distance.
	PARAMETERS:
		0 - at (POSITION): the middle of the barrage
		1 - rounds (NUMBER, default 30): how many shells
		2 - radius (NUMBER, default 120): how far from the middle they fall, in m
		3 - safety (NUMBER, default 250): the closest a player's side may be, in m; under 150 is refused
		4 - shell (STRING, default "Sh_155mm_AMOS"): the shell's class; Sh_82mm_AMOS for a mortar
	RETURNS: ["firing", closest friendly in m, or "none" with no player on the map] (ARRAY)
	TARGET: server
	TAGS: artillery, bombard, barrage, shells, explosions, fire support, mortar, strike
	EXAMPLE: {"at": [0, 0], "rounds": 1, "safety": 150}
*/
params ["_at", "_rounds", "_radius", "_safety", "_shell"];
if (_at isEqualTo []) exitWith {
	"ERROR: no such place"
};
if (_safety < 150) exitWith {
	"ERROR: the safety distance can't be under 150 m"
};
if (not isClass (configFile >> "CfgAmmo" >> _shell)) exitWith {
	format ["ERROR: there's no ammunition class %1", _shell]
};
private _friends = [];
{
	_friends append units group _x;
} forEach allPlayers;
private _closest = if (_friends isEqualTo []) then {
	1e6
} else {
	selectMin (_friends apply {
		_x distance2D _at
	})
};
if (_closest < _safety) exitWith {
	format ["ERROR: too close: a player's side is %1 m away, inside the %2 m safety distance", round _closest, _safety]
};
[_at, _rounds, _radius, _shell] spawn {
	params ["_at", "_rounds", "_radius", "_shell"];
	for "_i" from 1 to _rounds do {
		private _round = createVehicle [_shell, (_at getPos [random _radius, random 360]) vectorAdd [0, 0, 150], [], 0,
			"CAN_COLLIDE"];
		_round setVelocity [0, 0, -150];
		sleep 0.4;
	};
};
["firing", [round _closest, "none"] select (_friends isEqualTo [])]
