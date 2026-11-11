/*
	NAME: find_class
	DESCRIPTION: Find classes by their display name, such as "rpk", "hunter" or "ghost hawk": vehicles (and
		men, animals, objects), weapons (and items), or magazines. Only those placeable in a mission.
	PARAMETERS:
		0 - text (STRING): part of the display name, any case
		1 - kind (STRING, default "vehicle"): vehicle, weapon or magazine
		2 - limit (NUMBER, default 20): the most to return
	RETURNS: [[class, display name]] (ARRAY)
	TARGET: server
	TAGS: find, search, class, classname, weapon, vehicle, magazine, config, lookup
	EXAMPLE: {"text": "hunter"}
*/
params ["_text", "_kind", "_limit"];
private _root = switch (toLowerANSI _kind) do {
	case "vehicle": {
		"CfgVehicles"
	};
	case "weapon": {
		"CfgWeapons"
	};
	case "magazine": {
		"CfgMagazines"
	};
	default {
		""
	};
};
if (_root isEqualTo "") exitWith {
	"ERROR: kind must be vehicle, weapon or magazine"
};
private _wanted = toLowerANSI _text;
private _found = ("getNumber (_x >> 'scope') isEqualTo 2" configClasses (configFile >> _root)) select {
	(toLowerANSI getText (_x >> "displayName")) find _wanted >= 0
};
(_found select [0, _limit]) apply {
	[configName _x, getText (_x >> "displayName")]
}
