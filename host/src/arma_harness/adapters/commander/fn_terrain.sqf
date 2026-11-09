/*
	NAME: brmh_cmd_fnc_terrain
	DESCRIPTION: The ground around a place, as a commander's paper map would show it: heights, water and woods on a square
		grid, roads, the world's own buildings, and its named places. Only terrain: these commands see the world's own
		objects and its config, never anything a mission placed, which would put the enemy on the map. Named places come
		from the world's config for that reason, since a mission can create locations.
	PARAMETERS:
		0 - Centre [x, y] (ARRAY)
		1 - Radius, metres (NUMBER)
		2 - Cell size, metres (NUMBER)
	USAGE:
		[[3200, 2800], 1500, 50] call brmh_cmd_fnc_terrain;
	RETURNS: [[x0, y0, step, n], cells, roads, houses, places] (ARRAY), where:
		cells  - n * n of [height, water 0 or 1, trees, bushes], row by row from the south-west corner
		roads  - [x1, y1, x2, y2, kind], each stretch once
		houses - [x, y, width, length, direction]
		places - [name, type, x, y]
	ENVIRONMENT: Server
*/
params [["_centre", [], [[]], 2], ["_radius", 1000, [0]], ["_step", 50, [0]]];
private _n = ceil (2 * _radius / _step);
private _x0 = (_centre # 0) - _radius;
private _y0 = (_centre # 1) - _radius;
private _cells = [];
for "_j" from 0 to _n - 1 do {
	for "_i" from 0 to _n - 1 do {
		private _at = [_x0 + (_i + 0.5) * _step, _y0 + (_j + 0.5) * _step];
		_cells pushBack [
			round getTerrainHeightASL _at,
			[0, 1] select (surfaceIsWater _at),
			count (nearestTerrainObjects [_at, ["TREE", "SMALL TREE"], _step / 2, false, true]),
			count (nearestTerrainObjects [_at, ["BUSH"], _step / 2, false, true])
		];
	};
};
private _roads = [];
{
	private _from = getPosATL _x;
	private _kind = (getRoadInfo _x) # 0;
	{
		private _to = getPosATL _x;
		// Each stretch once: from its west end, or its south end when they're level.
		if ((_from # 0) < (_to # 0) or {
			(_from # 0) isEqualTo (_to # 0) and {
				(_from # 1) < (_to # 1)
			}
		}) then {
			_roads pushBack [round (_from # 0), round (_from # 1), round (_to # 0), round (_to # 1), _kind];
		};
	} forEach (roadsConnectedTo _x);
} forEach (_centre nearRoads (_radius * 1.42));
private _houses = (nearestTerrainObjects [_centre, ["HOUSE", "BUILDING", "CHURCH", "CHAPEL", "BUNKER", "FORTRESS", "VIEW-TOWER", "LIGHTHOUSE", "FUELSTATION", "HOSPITAL", "TRANSMITTER"], _radius * 1.42, false, true]) apply {
	private _box = boundingBoxReal _x;
	private _size = (_box # 1) vectorDiff (_box # 0);
	private _at = getPosATL _x;
	[round (_at # 0), round (_at # 1), round (_size # 0), round (_size # 1), round getDir _x]
};
private _places = (("true" configClasses (configFile >> "CfgWorlds" >> worldName >> "Names")) select {
	getText (_x >> "name") isNotEqualTo "" and {
		((getArray (_x >> "position")) distance2D _centre) <= _radius * 1.42
	}
}) apply {
	private _at = getArray (_x >> "position");
	[getText (_x >> "name"), getText (_x >> "type"), round (_at # 0), round (_at # 1)]
};
[[_x0, _y0, _step, _n], _cells, _roads, _houses, _places]
