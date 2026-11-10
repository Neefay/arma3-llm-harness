/*
	NAME: brmh_cmd_fnc_mirror
	DESCRIPTION: Shows one of the commander's map markers on the game's own map, for a human observer. One-way: nothing
		reads it back, so it can't help the commander.
	PARAMETERS:
		0 - Marker id (STRING)
		1 - Kind: enemy, friendly, objective, danger, hypothesis, phase_line, area or note; the last three are drawn
		    as a white dot (STRING)
		2 - Points, [[x, y], ...]; the first is where it's drawn (ARRAY)
		3 - Label (STRING)
		4 - Confidence, as the commander gave it: low, medium or high (STRING)
		5 - (OPTIONAL) Whether it was removed (BOOL) - Default: false
	USAGE:
		["E1", "enemy", [[4120, 4180]], "MG team", "medium"] call brmh_cmd_fnc_mirror;
		["E1", "enemy", [], "", "", true] call brmh_cmd_fnc_mirror;
	RETURNS: true
	ENVIRONMENT: Server, unscheduled (the host's exec)
*/
params [["_id", "", [""]], ["_kind", "note", [""]], ["_points", [], [[]]], ["_label", "", [""]], ["_confidence", "", [""]], ["_removed", false, [false]]];
private _name = "brmh_cmd_" + _id;
deleteMarker _name;
if (_removed) exitWith {
	true
};
private _marker = createMarker [_name, (_points # 0) + [0]];
// Local until the last change, which sends the marker's whole state once.
_marker setMarkerTypeLocal (createHashMapFromArray [["enemy", "mil_warning"], ["friendly", "mil_dot"], ["objective", "mil_objective"], ["danger", "mil_warning"], ["hypothesis", "mil_unknown"]] getOrDefault [_kind, "mil_dot"]);
_marker setMarkerColorLocal (createHashMapFromArray [["enemy", "ColorOPFOR"], ["friendly", "ColorBLUFOR"], ["objective", "ColorGreen"], ["danger", "ColorOrange"]] getOrDefault [_kind, "ColorWhite"]);
_marker setMarkerText (([_id, _label, _confidence] select {
	_x isNotEqualTo ""
}) joinString " ");
true
