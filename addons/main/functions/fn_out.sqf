/*
	NAME: BRMH_fnc_out
	DESCRIPTION: Server side of the event channel. Hands an envelope to the Python bridge, and mirrors
		it to the RPT when the bridge is down or the envelope is important (errors, machines). RPT lines
		are prefixed "[BRMH]" and chunked under the ~1 KB diag_log line limit.
	PARAMETERS:
		0 - Envelope (STRING, JSON)
	RETURNS: Nothing
	ENVIRONMENT: Server only
*/
params [["_json", "", [""]]];

if (brmh_bridgeActive) then {
	["brmh.bridge.emit", [_json]] call BRMH_fnc_bridgeCall;
};

private _mirror = not brmh_bridgeActive or {
	"""k"":""err""" in _json or {
		"""k"":""hello""" in _json
	}
};
if (not _mirror) exitWith {};

if (count _json <= 900) exitWith {
	diag_log text ("[BRMH] " + _json);
};
brmh_chunkSeq = brmh_chunkSeq + 1;
private _total = ceil ((count _json) / 900);
for "_i" from 0 to (_total - 1) do {
	diag_log text format ["[BRMH#%1:%2/%3] %4", brmh_chunkSeq, _i + 1, _total, _json select [_i * 900, 900]];
};
