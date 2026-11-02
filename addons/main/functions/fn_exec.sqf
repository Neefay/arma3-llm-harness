/*
	NAME: BRMH_fnc_exec
	DESCRIPTION: Executes one request on this machine and reports a "res" envelope.
		Unscheduled by default; script errors raised meanwhile are attached to the result (see
		BRMH_fnc_onScriptError). A request that aborts on an error is reported on the next frame by
		BRMH_fnc_onFrame. With "scheduled", the code is spawned and reports when it finishes.
	PARAMETERS:
		0 - Request: id (STRING), code (STRING), args (ARRAY, passed as _this), scheduled (BOOL) (HASHMAP)
	USAGE:
		[createHashMapFromArray [["id", "q1"], ["code", "1 + 1"]]] call BRMH_fnc_exec;
	RETURNS: Nothing
	ENVIRONMENT: Every machine, unscheduled
*/
params [["_request", createHashMap, [createHashMap]]];

private _id = _request getOrDefault ["id", "?"];
private _args = _request getOrDefault ["args", []];
["begin", createHashMapFromArray [["id", _id]]] call BRMH_fnc_emit;

// Marked current before compiling, so compile errors are attributed to this request in both modes.
brmh_current = _id;
brmh_errors = [];
// The prefix makes the request id visible in ScriptError's "content", which attributes errors
// raised later by code this request spawned.
private _code = compile format ["private _brmhReq = ""%1"";%2", _id, _request getOrDefault ["code", ""]];

if (brmh_errors isNotEqualTo []) exitWith {
	brmh_current = "";
	["res", createHashMapFromArray [
		["id", _id],
		["ok", false],
		["compile", false],
		["errors", brmh_errors]
	]] call BRMH_fnc_emit;
};

if (_request getOrDefault ["scheduled", false]) exitWith {
	brmh_current = "";
	private _handle = [_id, _code, _args] spawn {
		params ["_id", "_code", "_args"];
		private _t0 = diag_tickTime;
		private _result = _args call _code;
		brmh_scheduledDone set [_id, true];
		private _errors = brmh_scheduledErrors getOrDefault [_id, []];
		private _res = createHashMapFromArray [
			["id", _id],
			["ok", _errors isEqualTo []],
			["scheduled", true],
			["ms", (diag_tickTime - _t0) * 1000],
			["errors", _errors]
		];
		if (not isNil "_result") then {
			_res set ["r", [_result] call BRMH_fnc_sanitize];
		};
		["res", _res] call BRMH_fnc_emit;
	};
	brmh_scheduled pushBack [_id, _handle];
};

private _t0 = diag_tickTime;
private _result = _args call _code;
private _ms = (diag_tickTime - _t0) * 1000;
brmh_current = "";

private _res = createHashMapFromArray [
	["id", _id],
	["ok", brmh_errors isEqualTo []],
	["ms", _ms],
	["errors", brmh_errors]
];
if (not isNil "_result") then {
	_res set ["r", [_result] call BRMH_fnc_sanitize];
};
["res", _res] call BRMH_fnc_emit;
