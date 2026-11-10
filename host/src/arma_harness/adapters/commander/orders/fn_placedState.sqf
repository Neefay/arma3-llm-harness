// What a squad's placing machine is at, for the packet: -1 none, 0 moving, 1 placed.
params ["_group"];
private _at = brmh_cmd_builds findIf {
	(_x get "GROUP") isEqualTo _group and {
		((_x get "SPEC") get "KIND") isEqualTo "placing"
	} and {
		(_x get "STATE") isNotEqualTo ""
	}
};
if (_at < 0) exitWith {
	-1
};
parseNumber (((brmh_cmd_builds # _at) get "STATE") isEqualTo "placed")
