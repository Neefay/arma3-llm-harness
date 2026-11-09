// The pilot searching the grid he was given. The engine's own spotting from a fast jet or a helicopter misses men lying
// in grass even 74 m below (Stratis), so the search is modelled as Antistasi models it (fn_SUP_CASApproach): each enemy
// near the grid, if nothing blocks the line from the aircraft, has a chance each second of being seen, less the farther
// he is from the grid and from the aircraft, and less again lying down or crouching (that part is ours). Whoever is seen
// is revealed to the crew, and the engine's seek-and-destroy does the rest. An empty grid gets nothing.
params ["_machine"];
private _vehicle = _machine get "VEHICLE";
private _group = _machine get "GROUP";
private _aim = (_machine get "AIM") select [0, 2];
private _elapsed = time - (_machine getOrDefault ["SEARCHED", time]);
_machine set ["SEARCHED", time];
if (_elapsed <= 0) exitWith {};
private _eye = getPosASL _vehicle;
private _seen = [];
{
	private _target = vehicle _x;
	if (alive _x and {
		((side _group) getFriend (side group _x)) < 0.6
	} and {
		not (_target in _seen)
	}) then {
		private _at = if (_target isKindOf "CAManBase") then {
			eyePos _target
		} else {
			(getPosASL _target) vectorAdd [0, 0, 1.5]
		};
		if (not terrainIntersectASL [_at, _eye] and {
			not lineIntersects [_at, _eye, _target, _vehicle]
		}) then {
			private _stance = if (_target isKindOf "CAManBase") then {
				switch (stance _target) do {
					case "PRONE": {
						0.3
					};
					case "CROUCH": {
						0.6
					};
					default {
						1
					};
				}
			} else {
				1
			};
			private _camouflage = 1 max getNumber (configOf _target >> "camouflage");
			private _perSecond = 0.05 * _camouflage * _stance * exp ((_at distance2D _aim) / -500) * exp (
				(_at distance2D _eye) / -3000
			);
			if ((1 - (1 - (_perSecond min 1)) ^ _elapsed) > random 1) then {
				_seen pushBack _target;
			};
		};
	};
} forEach (allUnits inAreaArray [_aim, _machine get "RADIUS", _machine get "RADIUS"]);
{
	_group reveal [_x, 2.5];
} forEach _seen;
_machine set ["SPOTTED", (_machine getOrDefault ["SPOTTED", 0]) + count _seen];
