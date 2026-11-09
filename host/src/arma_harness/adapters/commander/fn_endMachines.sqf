// Ends a squad's machines of these kinds, as a new order does to the old one's.
params ["_group", "_kinds", ["_word", "called off"]];
{
	if ((_x get "GROUP") isEqualTo _group and {
		((_x get "SPEC") get "KIND") in _kinds
	}) then {
		_x call ["#END", [_word]];
	};
} forEach brmh_cmd_builds;
