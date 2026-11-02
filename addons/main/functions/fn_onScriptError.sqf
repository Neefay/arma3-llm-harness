/*
	NAME: BRMH_fnc_onScriptError
	DESCRIPTION: ScriptError mission event handler. Reports script errors as "err" envelopes and
		attributes them to the request that caused them: the request running right now (unscheduled), or
		the request whose compiled source starts with its "_brmhReq" tag (code it spawned).
		Repeats are collapsed, since an error inside a loop fires once per iteration: within a request the
		same error only increments "repeats" on the stored one (at most BRMH_MAX_ERRORS distinct errors are
		kept, the rest are counted in "more" on the first); an error no request owns is reported at most
		once per BRMH_ERROR_REPEAT_INTERVAL, with "repeats" counting the occurrences since the last report.
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

private _make = {
	createHashMapFromArray [
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
	]
};

if (_owner isEqualTo "") exitWith {
	private _key = str [_sourceFile, _lineNumber, _errorPos, _errorText];
	(brmh_looseErrors getOrDefault [_key, [-1e9, 0]]) params ["_last", "_suppressed"];
	if (diag_tickTime - _last < BRMH_ERROR_REPEAT_INTERVAL) exitWith {
		brmh_looseErrors set [_key, [_last, _suppressed + 1]];
	};
	brmh_looseErrors set [_key, [diag_tickTime, 0]];
	private _err = call _make;
	if (_suppressed > 0) then {
		_err set ["repeats", _suppressed + 1];
	};
	["err", _err] call BRMH_fnc_emit;
};

private _list = if (brmh_current isNotEqualTo "") then {
	brmh_errors
} else {
	brmh_scheduledErrors getOrDefaultCall [_owner, {
		[]
	}, true]
};
private _same = _list findIf {
	(_x get "line") isEqualTo _lineNumber and {
		(_x get "pos") isEqualTo _errorPos
	} and {
		(_x get "file") isEqualTo _sourceFile
	} and {
		(_x get "text") isEqualTo _errorText
	}
};
if (_same >= 0) exitWith {
	private _stored = _list # _same;
	_stored set ["repeats", (_stored getOrDefault ["repeats", 1]) + 1];
};
if (count _list >= BRMH_MAX_ERRORS) exitWith {
	private _first = _list # 0;
	_first set ["more", (_first getOrDefault ["more", 0]) + 1];
};

private _err = call _make;
_list pushBack _err;
// A copy: emit adds envelope fields, which do not belong in the stored error.
["err", +_err] call BRMH_fnc_emit;
