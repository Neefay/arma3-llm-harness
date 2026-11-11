/*
	NAME: player_info
	DESCRIPTION: Where someone is and what they're doing: their grid, position, facing, vehicle, squad and side.
		Start here for anything "near me" or "in front of me".
	PARAMETERS:
		0 - who (OBJECT, default "player"): whose
	RETURNS: {name, grid, pos [x, y, z ATL], dir, vehicle (class, or ""), squad (names), side} (HASHMAP)
	TARGET: server
	TAGS: player, position, where, grid, facing, squad, me
	EXAMPLE: {}
*/
params ["_who"];
if (isNull _who) exitWith {
	"ERROR: no such unit: use player, a name, or a net id"
};
createHashMapFromArray [
	["name", name _who],
	["grid", mapGridPosition _who],
	["pos", (getPosATL _who) apply {
		round _x
	}],
	["dir", round getDir _who],
	["vehicle", [typeOf vehicle _who, ""] select (vehicle _who isEqualTo _who)],
	["squad", (units group _who) apply {
		name _x
	}],
	["side", str side group _who]
]
