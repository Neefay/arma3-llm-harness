/*
	NAME: brmh_cmd_fnc_shellOnPosts
	DESCRIPTION: A shell that bursts within 20 m of an aid post damages it, less the further out: up to 0.4 a round.
		One 82 mm round on a tent did 0.38 by the engine's own reckoning, when it was allowed to. Smoke does nothing.
	PARAMETERS:
		0 - Where it burst (ARRAY)
		1 - Its ammo class (STRING)
	USAGE:
		[_pos, typeOf _shell] call brmh_cmd_fnc_shellOnPosts;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled (a shell's Explode handler)
*/
params ["_pos", "_ammo"];
if ("smoke" in toLowerANSI _ammo) exitWith {};
{
	private _away = _x distance2D [_pos # 0, _pos # 1];
	if (alive _x and {
		_away < 20
	}) then {
		_x allowDamage true;
		_x setDamage ((damage _x) + (0.4 * (1 - (_away / 20))));
		_x allowDamage false;
	};
} forEach brmh_cmd_posts;
