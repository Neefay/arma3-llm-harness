/*
	NAME: BRMH_fnc_bridgeCall
	DESCRIPTION: Calls a Python function through Pythia without py3_fnc_callExtension's side effects
		(that one shows Python errors in systemChat and returns [] for both errors and empty results).
		Handles Pythia's multipart responses for large return values.
	PARAMETERS:
		0 - Python function, "package.module.function" (STRING)
		1 - Arguments: strings, numbers, booleans and arrays only (ARRAY)
	USAGE:
		(["brmh.bridge.poll", []] call BRMH_fnc_bridgeCall) params ["_ok", "_value"];
	RETURNS: [success (BOOL), value or error message (ANY)]
	ENVIRONMENT: Any machine with @Pythia loaded
*/
params [["_function", "", [""]], ["_args", [], [[]]]];

private _raw = "Pythia" callExtension (str [_function, _args]);
if (_raw isEqualTo "") exitWith {
	[false, "empty response (Pythia not loaded?)"]
};

if ((_raw select [2, 1]) isEqualTo "m") then {
	private _header = parseSimpleArray _raw;
	private _stitched = "";
	for "_i" from 1 to (_header # 2) do {
		_stitched = _stitched + ("Pythia" callExtension (str ["pythia.multipart", _header # 1]));
	};
	_raw = _stitched;
};

switch (_raw select [2, 1]) do {
	case "r": {
		[true, (parseSimpleArray _raw) # 1]
	};
	case "e": {
		[false, (parseSimpleArray _raw) # 1]
	};
	default {
		[false, "unknown Pythia response: " + (_raw select [0, 200])]
	};
}
