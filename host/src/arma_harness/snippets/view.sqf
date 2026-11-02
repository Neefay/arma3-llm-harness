/*
	Structured "what is on the player's screen" (comments are stripped by the host), to ground a
	screenshot in things that can be acted on. _this: [radius, maxObjects]
	Each object: type, name, position (ATL), distance, screen [x, y] (0..1 of the screen, from
	worldToScreen), seen (0..1, how unobstructed the line of sight is), plus building positions for
	buildings and side for units and vehicles. Small clutter (walls, fences, signs) is skipped.
*/
params [["_radius", 300, [0]], ["_max", 40, [0]]];
private _eye = positionCameraToWorld [0, 0, 0];
private _eyeASL = AGLToASL _eye;
private _toScreen = {
	params ["_pos"];
	private _s = worldToScreen _pos;
	if (_s isEqualTo []) exitWith {
		[]
	};
	// Normalise from UI coordinates to 0..1 of the visible screen.
	private _sx = ((_s # 0) - safeZoneX) / safeZoneW;
	private _sy = ((_s # 1) - safeZoneY) / safeZoneH;
	if (_sx < 0 or {
		_sx > 1
	} or {
		_sy < 0
	} or {
		_sy > 1
	}) exitWith {
		[]
	};
	[round (_sx * 100) / 100, round (_sy * 100) / 100]
};

private _candidates = nearestObjects [_eye, ["House", "Building", "LandVehicle", "Air", "Ship", "CAManBase", "StaticWeapon"], _radius] select {
	_x isNotEqualTo player and {
		_x isNotEqualTo vehicle player
	} and {
		not (_x isKindOf "CAManBase" and {
			not alive _x
		})
	} and {
		not (_x isKindOf "House" or {
			_x isKindOf "Building"
		}) or {
			count (_x buildingPos -1) > 0
		} or {
			((boundingBoxReal _x) # 1 # 2) - ((boundingBoxReal _x) # 0 # 2) >= 6
		}
	}
};
private _visible = [];
{
	private _bb = boundingBoxReal _x;
	private _centerASL = (getPosASLVisual _x) vectorAdd [0, 0, ((_bb # 1 # 2) - (_bb # 0 # 2)) * 0.5];
	private _screen = [ASLToAGL _centerASL] call _toScreen;
	if (_screen isNotEqualTo []) then {
		private _info = createHashMapFromArray [
			["type", typeOf _x],
			["name", getText (configOf _x >> "displayName")],
			["pos", (getPosATL _x) apply {
				round _x
			}],
			["distance", round (_eye distance _x)],
			["screen", _screen],
			["seen", round (([vehicle player, "VIEW", _x] checkVisibility [_eyeASL, _centerASL]) * 100) / 100]
		];
		if (_x isKindOf "House" or {
			_x isKindOf "Building"
		}) then {
			_info set ["buildingPositions", count (_x buildingPos -1)];
			_info set ["height", round ((_bb # 1 # 2) - (_bb # 0 # 2))];
		} else {
			_info set ["side", str side group _x];
			_info set ["alive", alive _x];
		};
		_visible pushBack _info;
	};
	if (count _visible >= _max) exitWith {};
} forEach _candidates;

private _places = nearestLocations [getPosATL player, ["NameCityCapital", "NameCity", "NameVillage", "NameLocal", "NameMarine", "Hill"], 5000];
private _nearest = if (_places isEqualTo []) then {
	["", -1]
} else {
	[text (_places # 0), round (player distance2D (locationPosition (_places # 0)))]
};
createHashMapFromArray [
	["player", createHashMapFromArray [
		["pos", (getPosATL player) apply {
			round _x
		}],
		["dir", round getDir player],
		["grid", mapGridPosition player],
		["stance", stance player],
		["vehicle", if (vehicle player isEqualTo player) then {
			""
		} else {
			typeOf vehicle player
		}],
		["nearestLocation", _nearest]
	]],
	["camera", createHashMapFromArray [
		["pos", _eye apply {
			round _x
		}],
		["dir", round ((positionCameraToWorld [0, 0, 1]) getDir (positionCameraToWorld [0, 0, 100]))]
	]],
	["world", createHashMapFromArray [
		["name", worldName],
		["daytime", round (daytime * 100) / 100],
		["date", date],
		["overcast", round (overcast * 100) / 100],
		["rain", round (rain * 100) / 100],
		["fog", round (fog * 100) / 100]
	]],
	["visible", _visible]
]
