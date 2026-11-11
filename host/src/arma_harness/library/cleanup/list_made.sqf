/*
	NAME: list_made
	DESCRIPTION: Everything the library has made this mission, by handle: what it is, how many things, and how
		many are still there.
	RETURNS: [[handle, what, things, still there]] (ARRAY)
	TARGET: server
	TAGS: list, made, handles, spawned, created, inventory
	EXAMPLE: {}
*/
(keys brmh_lib_made) apply {
	(brmh_lib_made get _x) params ["_things", "_note"];
	[_x, _note, count _things, {
		not isNull _x
	} count _things]
}
