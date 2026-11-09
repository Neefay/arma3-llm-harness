// One 82 mm round on a tent did 0.38 by the engine's own reckoning, when it was allowed to.
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
