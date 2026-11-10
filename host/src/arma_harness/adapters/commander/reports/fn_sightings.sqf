/*
	NAME: brmh_cmd_fnc_sightings
	DESCRIPTION: What a squad can see of empty or wrecked vehicles and destroyed buildings, within 800 m of its first
		able man. The host decides what's news. Only one squad per monitor step does this, because it's the most
		expensive thing here. A vehicle seen for the first time gets a key ("U" and a number) in brmh_cmd_vehicles.
	PARAMETERS:
		0 - Group (GROUP)
	USAGE:
		[_group] call brmh_cmd_fnc_sightings;
	RETURNS: Nothing. Sets the group's brmh_cmd_seenVehicles ([[key, display name, grid, alive], ...]) and
		brmh_cmd_seenRuins ([building id, ...]), which the packet sends
	ENVIRONMENT: Server, unscheduled (the 2 s monitor, brmh_cmd_fnc_step)
*/
params ["_group"];
private _alive = (units _group) select {
	[_x] call brmh_cmd_fnc_able
};
if (_alive isEqualTo []) exitWith {};
private _lookers = _alive select [0, 4];
private _leader = _alive # 0;
private _vehicles = (_leader nearEntities [["StaticWeapon", "LandVehicle"], 800]) select {
	({
		alive _x
	} count crew _x) isEqualTo 0
};
{
	if (not alive _y and {
		_leader distance2D _y < 800
	}) then {
		_vehicles pushBackUnique _y;
	};
} forEach brmh_cmd_vehicles;
private _seen = [];
{
	private _vehicle = _x;
	private _top = (getPosASL _vehicle) vectorAdd [0, 0, 1];
	// A burning wreck's own smoke blocks VIEW, even from beside it. FIRE ignores smoke.
	if ([_lookers, _vehicle, _top, ["FIRE", "VIEW"] select alive _vehicle] call brmh_cmd_fnc_canSee) then {
		private _key = _vehicle getVariable ["brmh_cmd_key", ""];
		if (_key isEqualTo "") then {
			// A counter of its own: one taken from the list's size would repeat once anything left the list.
			brmh_cmd_unknownCount = (missionNamespace getVariable ["brmh_cmd_unknownCount", 0]) + 1;
			_key = format ["U%1", brmh_cmd_unknownCount];
			_vehicle setVariable ["brmh_cmd_key", _key];
			brmh_cmd_vehicles set [_key, _vehicle];
		};
		_seen pushBack [_key, getText (configOf _vehicle >> "displayName"), mapGridPosition _vehicle, alive _vehicle];
	};
} forEach _vehicles;
_group setVariable ["brmh_cmd_seenVehicles", _seen];
private _ruins = [];
{
	if (_leader distance2D _y < 800 and {
		isNull ([_y] call brmh_cmd_fnc_building)
	}) then {
		private _ground = [_y # 0, _y # 1, (getTerrainHeightASL _y) + 1];
		if ([_lookers, objNull, _ground, "FIRE"] call brmh_cmd_fnc_canSee) then {
			_ruins pushBack _x;
		};
	};
} forEach brmh_cmd_buildings;
_group setVariable ["brmh_cmd_seenRuins", _ruins];
