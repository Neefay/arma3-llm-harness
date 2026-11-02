/*
	NAME: BRMH_fnc_route
	DESCRIPTION: Hub routing. Resolves a request's target to machines, announces the dispatch (so the
		host knows how many results to wait for), and hands the request to each machine.
	PARAMETERS:
		0 - Request: id, code, target, scheduled, args (HASHMAP)
	USAGE:
		[_request] call BRMH_fnc_route;
	RETURNS: Nothing
	ENVIRONMENT: Server only, unscheduled
*/
params [["_request", createHashMap, [createHashMap]]];

private _id = _request getOrDefault ["id", "?"];
private _target = _request getOrDefault ["target", "server"];
private _owners = [_target] call BRMH_fnc_resolveTargets;

["dispatch", createHashMapFromArray [
	["id", _id],
	["target", _target],
	["owners", _owners]
]] call BRMH_fnc_emit;

private _json = toJSON _request;
{
	if (_x isEqualTo clientOwner) then {
		brmh_queue pushBack _request;
	} else {
		["brmh_req", [_json], _x] call CBA_fnc_ownerEvent;
	};
} forEach _owners;
