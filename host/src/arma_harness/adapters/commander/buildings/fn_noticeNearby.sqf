/*
	NAME: brmh_cmd_fnc_noticeNearby
	DESCRIPTION: AI won't register an enemy it walks past, so a man clearing rooms is told of every enemy within 10 m.
		Only what a soldier could plainly see from where he stands counts, so it isn't a cheat.
	PARAMETERS:
		0 - Soldier (OBJECT)
	USAGE:
		[_soldier] call brmh_cmd_fnc_noticeNearby;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_soldier"];
private _side = side group _soldier;
{
	if (alive _x and {
		(_side getFriend side group _x) < 0.6
	} and {
		([vehicle _soldier, "VIEW", _x] checkVisibility [eyePos vehicle _soldier, eyePos _x]) > 0.3
	}) then {
		_soldier reveal [_x, 4];
	};
} forEach (_soldier nearEntities ["CAManBase", 10]);
