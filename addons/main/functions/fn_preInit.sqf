/*
	NAME: BRMH_fnc_preInit
	DESCRIPTION: Initialises the harness probe. Every machine runs the agent part (exec, events); the
		server additionally runs the hub (bridge poll, routing, machine registry).
		The probe is inert unless the arma-harness host wrote a session file for this game process:
		without one, the Python bridge never starts and nothing is executed.
	PARAMETERS: None
	USAGE: Runs automatically (CfgFunctions preInit).
	RETURNS: Nothing
	ENVIRONMENT: Every machine, preInit, unscheduled
*/

BRMH_VERSION = "0.2.0";
BRMH_MACHINE = if (isServer) then {
	"SERVER"
} else {
	["HC", "CLIENT"] select hasInterface
};
brmh_current = "";
brmh_errors = [];
brmh_queue = [];
brmh_scheduled = [];
brmh_scheduledErrors = createHashMap;
brmh_scheduledDone = createHashMap;
brmh_machines = createHashMap;
brmh_looseErrors = createHashMap;
brmh_chunkSeq = 0;
// An error inside a loop fires once per iteration: a request keeps this many distinct errors (repeats
// are counted, not stored), and an error no request owns is reported at most once per interval (s).
BRMH_MAX_ERRORS = 20;
BRMH_ERROR_REPEAT_INTERVAL = 1;
// Envelopes larger than this (characters) are not mirrored to the RPT, only noted there.
BRMH_MIRROR_MAX = 16000;
BRMH_PYTHIA = isClass (configFile >> "CfgPatches" >> "PY3_Pythia");
brmh_bridgeActive = false;
brmh_bridgeCheckNext = 0;
// The session-file check is cheap but not free; inactive machines retry this often (attach support).
BRMH_BRIDGE_CHECK_INTERVAL = 2;

addMissionEventHandler ["ScriptError", {
	_this call BRMH_fnc_onScriptError;
}];

addMissionEventHandler ["ExtensionCallback", {
	params ["_name", "_function", "_data"];
	if (_name isEqualTo "brmh") then {
		private _parsed = if ((_data select [0, 1]) isEqualTo "[") then {
			parseSimpleArray _data
		} else {
			_data
		};
		["ext", createHashMapFromArray [
			["func", _function],
			["data", [_parsed] call BRMH_fnc_sanitize]
		]] call BRMH_fnc_emit;
	};
}];

// EachFrame (not a CBA PFH): PFHs only start after postInit, and requests must work from preInit on.
addMissionEventHandler ["EachFrame", {
	call BRMH_fnc_onFrame;
}];

["brmh_req", {
	params [["_json", "", [""]]];
	private _request = fromJSON _json;
	if (_request isEqualType createHashMap) then {
		brmh_queue pushBack _request;
	};
}] call CBA_fnc_addEventHandler;

if (isServer) then {
	["brmh_out", {
		params [["_json", "", [""]]];
		[_json] call BRMH_fnc_out;
	}] call CBA_fnc_addEventHandler;

	["brmh_hello", {
		_this call BRMH_fnc_register;
	}] call CBA_fnc_addEventHandler;

	addMissionEventHandler ["PlayerDisconnected", {
		params ["_id", "_uid", "_name", "_jip", "_owner"];
		if (_owner in brmh_machines) then {
			brmh_machines deleteAt _owner;
			["bye", createHashMapFromArray [
				["owner", _owner],
				["name", _name]
			]] call BRMH_fnc_emit;
		};
	}];
};
