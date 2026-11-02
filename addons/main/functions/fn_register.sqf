/*
	NAME: BRMH_fnc_register
	DESCRIPTION: Hub machine registry: stores a machine's hello, keyed by the owner id it reports.
		The payload is trusted over remoteExecutedOwner, which was observed as 0 for hellos sent
		during a headless client's initialisation.
	PARAMETERS:
		0 - Machine info (STRING, JSON object with at least "o" and "kind")
	RETURNS: Nothing
	ENVIRONMENT: Server only, "brmh_hello" CBA event
*/
params [["_json", "", [""]]];

private _info = fromJSON _json;
if (not (_info isEqualType createHashMap)) exitWith {};
private _owner = _info getOrDefault ["o", -1];
if (_owner < 0) exitWith {};
brmh_machines set [_owner, _info];
