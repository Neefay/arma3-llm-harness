/*
	NAME: BRMH_fnc_postInit
	DESCRIPTION: Announces this machine to the hub (machine registry) and to the event stream.
		Runs after JIP initialisation, so late joiners register too.
	PARAMETERS: None
	USAGE: Runs automatically (CfgFunctions postInit).
	RETURNS: Nothing
	ENVIRONMENT: Every machine, postInit, unscheduled
*/

// The Rust extension ships in the same mod; a ping tells the host whether capture tools are usable here.
private _ping = "brmh" callExtension ["ping", ["probe"]];
private _info = createHashMapFromArray [
	["kind", BRMH_MACHINE],
	["o", clientOwner],
	["iface", hasInterface],
	["name", profileName],
	["jip", didJIP],
	["build", productVersion # 3],
	["probe", BRMH_VERSION],
	["mission", missionName],
	["world", worldName],
	["pythia", BRMH_PYTHIA],
	["brmh_ext", (_ping # 0) isEqualTo "pong:probe"]
];
["hello", +_info] call BRMH_fnc_emit;
["brmh_hello", [toJSON _info]] call CBA_fnc_serverEvent;
