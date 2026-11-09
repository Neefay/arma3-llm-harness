// AI won't register an enemy it walks past. Only what a soldier could plainly see from here counts, so it isn't a cheat.
params ["_soldier"];
private _side = side group _soldier;
{
	if (alive _x and {
		(_side getFriend side group _x) < 0.6
	} and {
		([_soldier, "VIEW", _x] checkVisibility [eyePos _soldier, eyePos _x]) > 0.3
	}) then {
		_soldier reveal [_x, 4];
	};
} forEach (_soldier nearEntities ["CAManBase", 10]);
