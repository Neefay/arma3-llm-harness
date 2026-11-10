// What a squad's clearing is at, for the packet: [positions left (-1 none, 0 done), cleared, ruined, blocked].
params ["_group"];
private _at = brmh_cmd_builds findIf {
	(_x get "GROUP") isEqualTo _group and {
		((_x get "SPEC") get "KIND") isEqualTo "clearing"
	} and {
		(_x get "STATE") isNotEqualTo ""
	}
};
if (_at < 0) exitWith {
	[-1, [], [], []]
};
private _machine = brmh_cmd_builds # _at;
private _left = 0;
if ((_machine get "STATE") isNotEqualTo "done") then {
	_left = (_machine get "BUSY") + count (_machine get "SPOTS");
	{
		_left = _left + count (([_x # 1] call brmh_cmd_fnc_building) buildingPos -1);
	} forEach (_machine get "QUEUE");
	_left = _left max 1;
};
[_left, _machine get "CLEARED", _machine get "RUINED", _machine get "BLOCKED"]
