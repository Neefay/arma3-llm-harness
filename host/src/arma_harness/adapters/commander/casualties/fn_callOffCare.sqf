/*
	NAME: brmh_cmd_fnc_callOffCare
	DESCRIPTION: The squad's newest order says to do something else, so its men stop carrying, treating and building,
		and go back to it. A casualty's left where he is. A man being put in a vehicle is a moment from done, so he's
		let finish. Each man still waiting on a TREAT order is reported called off. Every other job of the squad's in
		brmh_cmd_builds ends as well, a sortie or a clearing as much as an aid post, except a task or a boarding.
	PARAMETERS:
		0 - Group (GROUP)
	USAGE:
		[_group] call brmh_cmd_fnc_callOffCare;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
params [["_group", grpNull, [grpNull]]];
{
	if ((_x get "GROUP") isEqualTo _group and {
		not ((_x get "STATE") in ["loading", ""])
	}) then {
		_x call ["#END", [["left", "put down"] select (not isNull attachedTo (_x get "SUBJECT"))]];
	};
} forEach brmh_cmd_carries;
brmh_cmd_carries = brmh_cmd_carries select {
	(_x get "STATE") isNotEqualTo ""
};
{
	private _treat = _x;
	if ((_treat get "GROUP") isEqualTo _group) then {
		{
			[_group, _treat get "ORDER", "treat", _x, "called off"] call brmh_cmd_fnc_careSay;
		} forEach (_treat get "QUEUE");
		_treat set ["QUEUE", []];
	};
} forEach brmh_cmd_treats;
{
	// A replaced task is still releasing the squad from CBA's scripts, and stopMount says how a boarding was stopped.
	if ((_x get "GROUP") isEqualTo _group and {
		not (((_x get "SPEC") get "KIND") in ["task", "boarding"])
	}) then {
		_x call ["#END", ["called off"]];
	};
} forEach brmh_cmd_builds;
brmh_cmd_builds = brmh_cmd_builds select {
	(_x get "STATE") isNotEqualTo ""
};
