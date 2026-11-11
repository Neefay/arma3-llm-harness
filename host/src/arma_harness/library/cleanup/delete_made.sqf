/*
	NAME: delete_made
	DESCRIPTION: Delete what a command made, by the handle it returned ("made:3"): vehicles with their crews,
		groups with their men, props and arrows. "all" deletes everything the library has made this mission.
	PARAMETERS:
		0 - handle (STRING): a "made:N" handle, or "all"
	RETURNS: how many objects were deleted (NUMBER)
	TARGET: server
	TAGS: delete, remove, clean up, undo, despawn, clear
	EXAMPLE: {"handle": "all"}
*/
params ["_handle"];
private _key = toLowerANSI _handle;
private _handles = if (_key isEqualTo "all") then {
	keys brmh_lib_made
} else {
	[_key]
};
if (_key isNotEqualTo "all" and {not (_key in brmh_lib_made)}) exitWith {
	format ["ERROR: no %1: list_made shows the handles there are", _handle]
};
private _deleted = 0;
{
	private _things = (brmh_lib_made getOrDefault [_x, [[], ""]]) # 0;
	{
		if (_x isEqualType grpNull) then {
			{
				deleteVehicle _x;
				_deleted = _deleted + 1;
			} forEach units _x;
			deleteGroup _x;
		} else {
			if (not isNull _x) then {
				{
					deleteVehicle _x;
				} forEach (crew _x select {
					not isPlayer _x
				});
				deleteVehicle _x;
				_deleted = _deleted + 1;
			};
		};
	} forEach _things;
	brmh_lib_made deleteAt _x;
} forEach _handles;
_deleted
