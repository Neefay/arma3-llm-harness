/*
	NAME: BRMH_fnc_emit
	DESCRIPTION: Sends one envelope to the host. Adds the common fields, serialises to JSON and
		forwards it to the server, which hands it to the bridge (and the RPT, see BRMH_fnc_out).
	PARAMETERS:
		0 - Envelope kind: "res", "err", "evt", "hello", ... (STRING)
		1 - Fields, JSON-safe values only (HASHMAP)
	USAGE:
		["evt", createHashMapFromArray [["type", "custom"], ["value", 42]]] call BRMH_fnc_emit;
	RETURNS: Nothing
	ENVIRONMENT: Any machine
*/
params [["_kind", "", [""]], ["_fields", createHashMap, [createHashMap]]];

_fields set ["v", 1];
_fields set ["k", _kind];
_fields set ["m", BRMH_MACHINE];
_fields set ["o", clientOwner];
_fields set ["t", CBA_missionTime];
_fields set ["tt", diag_tickTime];
_fields set ["f", diag_frameNo];

private _json = toJSON _fields;
if (isServer) then {
	[_json] call BRMH_fnc_out;
} else {
	["brmh_out", [_json]] call CBA_fnc_serverEvent;
};
