/*
	NAME: brmh_cmd_fnc_clearNext
	DESCRIPTION: A clearing goes into the next building in its queue: the positions a man can be sent to, and how many
		it has in all, which is what "checked" is measured against. Only the clearing machine calls it, once it has seen
		that the building is still standing.
	PARAMETERS:
		0 - Clearing machine, its QUEUE not empty (HASHMAP object)
	USAGE:
		[_this] call brmh_cmd_fnc_clearNext;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
private _next = (_machine get "QUEUE") deleteAt 0;
private _building = [_next # 1] call brmh_cmd_fnc_building;
_machine set ["CURRENT", _next # 0];
_machine set ["SPOTS", [_building] call brmh_cmd_fnc_safePositions];
_machine set ["REACHED", 0];
_machine set ["OF", count (_building buildingPos -1)];
{
	_x setVariable ["brmh_cmd_clearSpot", nil];
} forEach units (_machine get "GROUP");
