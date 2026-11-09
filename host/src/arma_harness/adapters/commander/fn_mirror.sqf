params [["_id", "", [""]], ["_kind", "note", [""]], ["_points", [], [[]]], ["_label", "", [""]], ["_confidence", "", [""]], ["_removed", false, [false]]];
private _name = "brmh_cmd_" + _id;
deleteMarker _name;
if (_removed) exitWith {
	true
};
private _marker = createMarker [_name, (_points # 0) + [0]];
_marker setMarkerType (createHashMapFromArray [["enemy", "mil_warning"], ["friendly", "mil_dot"], ["objective", "mil_objective"], ["danger", "mil_warning"], ["hypothesis", "mil_unknown"]] getOrDefault [_kind, "mil_dot"]);
_marker setMarkerColor (createHashMapFromArray [["enemy", "ColorOPFOR"], ["friendly", "ColorBLUFOR"], ["objective", "ColorGreen"], ["danger", "ColorOrange"]] getOrDefault [_kind, "ColorWhite"]);
_marker setMarkerText (([_id, _label, _confidence] select {
	_x isNotEqualTo ""
}) joinString " ");
true
