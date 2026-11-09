// A squad's boarding machine that's still running, or nothing.
params ["_group"];
private _at = brmh_cmd_builds findIf {
	(_x get "GROUP") isEqualTo _group and {
		((_x get "SPEC") get "KIND") isEqualTo "boarding"
	} and {
		(_x get "STATE") isNotEqualTo ""
	}
};
if (_at < 0) then {
	nil
} else {
	brmh_cmd_builds # _at
}
