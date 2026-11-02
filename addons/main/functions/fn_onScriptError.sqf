/*
	NAME: BRMH_fnc_onScriptError
	DESCRIPTION: ScriptError mission event handler. Reports every script error as an "err" envelope and
		attributes it to the request that caused it: the request running right now (unscheduled), or the
		request whose compiled source starts with its "_brmhReq" tag (code it spawned).
	PARAMETERS: The ScriptError event handler arguments
	RETURNS: Nothing
	ENVIRONMENT: Every machine, event handler
*/
params ["_errorText", "_sourceFile", "_lineNumber", "_errorPos", "_content", "_stackTraceOutput"];

private _owner = brmh_current;
private _tag = "private _brmhReq = """;
if (_owner isEqualTo "" and {
	_content find _tag isEqualTo 0
}) then {
	private _rest = _content select [count _tag];
	_owner = _rest select [0, _rest find """"];
};

private _err = createHashMapFromArray [
	["id", _owner],
	["scheduled", brmh_current isEqualTo "" and {
		_owner isNotEqualTo ""
	}],
	["text", _errorText],
	["file", _sourceFile],
	["line", _lineNumber],
	["pos", _errorPos],
	["near", _content select [(_errorPos - 40) max 0, 80]],
	["stack", _stackTraceOutput apply {
		[_x # 0, _x # 1, _x # 2, keys (_x # 3)]
	}]
];

if (brmh_current isNotEqualTo "") then {
	brmh_errors pushBack _err;
} else {
	if (_owner isNotEqualTo "") then {
		(brmh_scheduledErrors getOrDefaultCall [_owner, {[]}, true]) pushBack _err;
	};
};
["err", _err] call BRMH_fnc_emit;
