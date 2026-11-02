/*
	NAME: BRMH_fnc_onFrame
	DESCRIPTION: Per-frame work: reports aborted requests, finalises scheduled requests that died,
		polls the bridge (server) and executes queued requests (every machine).
	ENVIRONMENT: Every machine, EachFrame mission event handler, unscheduled
*/

// A script error aborts the rest of the handler that ran the request, so a request still marked
// current on the next frame never finished: report it, keep the queue for the others.
if (brmh_current isNotEqualTo "") then {
	["res", createHashMapFromArray [
		["id", brmh_current],
		["ok", false],
		["aborted", true],
		["errors", brmh_errors]
	]] call BRMH_fnc_emit;
	brmh_current = "";
};

// Scheduled requests report themselves when they finish; a dead one never does.
if (brmh_scheduled isNotEqualTo []) then {
	brmh_scheduled = brmh_scheduled select {
		_x params ["_id", "_handle"];
		if (scriptDone _handle) then {
			if (not (_id in brmh_scheduledDone)) then {
				["res", createHashMapFromArray [
					["id", _id],
					["ok", false],
					["aborted", true],
					["scheduled", true],
					["errors", brmh_scheduledErrors getOrDefault [_id, []]]
				]] call BRMH_fnc_emit;
			};
			brmh_scheduledDone deleteAt _id;
			brmh_scheduledErrors deleteAt _id;
			false
		} else {
			true
		};
	};
};

if (isServer and {
	BRMH_PYTHIA
}) then {
	if (brmh_bridgeActive) then {
		(["brmh.bridge.poll", []] call BRMH_fnc_bridgeCall) params ["_ok", "_items"];
		if (_ok and {
			_items isEqualType []
		}) then {
			{
				private _request = fromJSON _x;
				if (_request isEqualType createHashMap) then {
					[_request] call BRMH_fnc_route;
				};
			} forEach _items;
		};
	} else {
		if (diag_tickTime > brmh_bridgeCheckNext) then {
			brmh_bridgeCheckNext = diag_tickTime + BRMH_BRIDGE_CHECK_INTERVAL;
			(["brmh.bridge.start", [missionName, worldName]] call BRMH_fnc_bridgeCall) params ["_ok", "_state"];
			if (_ok and {
				(_state param [0, false]) isEqualTo true
			}) then {
				brmh_bridgeActive = true;
				["bridge", createHashMapFromArray [
					["state", "active"],
					["port", _state param [1, 0]]
				]] call BRMH_fnc_emit;
				// Hellos sent before activation only reached the RPT; replay the registry for the host.
				{
					["hello", +_y] call BRMH_fnc_emit;
				} forEach brmh_machines;
			};
		};
	};
};

while {
	brmh_queue isNotEqualTo []
} do {
	[brmh_queue deleteAt 0] call BRMH_fnc_exec;
};
