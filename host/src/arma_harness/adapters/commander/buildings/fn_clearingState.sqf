/*
	NAME: brmh_cmd_fnc_clearingState
	DESCRIPTION: What a squad's clearing is at, for the packet. Positions left counts the buildings still queued too,
		and stays at 1 or more until the machine is done, so 0 only ever means finished.
	PARAMETERS:
		0 - Group (GROUP)
	USAGE:
		([_group] call brmh_cmd_fnc_clearingState) params ["_left", "_cleared", "_ruined", "_blocked"];
	RETURNS: [positions left (-1 no clearing, 0 done), cleared ids, ruined ids, blocked [[id, reached, of], ...]]
		(ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
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
