/*
	NAME: BRMH_fnc_resolveTargets
	DESCRIPTION: Resolves a target selector to machine owner ids, using the hub's machine registry.
	PARAMETERS:
		0 - Target (STRING): one of
			"server", "all", "clients" (machines with a player interface, except the server),
			"hcs", "interface" (every machine with a player interface, server-host included),
			"owner:<n>", "player:<profile name>"
	USAGE:
		["hcs"] call BRMH_fnc_resolveTargets; // [4, 5]
		["player:Nife"] call BRMH_fnc_resolveTargets;
	RETURNS: Owner ids (ARRAY of NUMBER), empty when nothing matches
	ENVIRONMENT: Server only
*/
params [["_target", "server", [""]]];

private _byKind = {
	params ["_kinds"];
	(keys brmh_machines) select {
		((brmh_machines get _x) getOrDefault ["kind", ""]) in _kinds
	}
};

switch (true) do {
	case (_target isEqualTo "server"): {
		[clientOwner]
	};
	case (_target isEqualTo "all"): {
		private _all = (keys brmh_machines) + [clientOwner];
		_all arrayIntersect _all
	};
	case (_target isEqualTo "clients"): {
		[["CLIENT"]] call _byKind
	};
	case (_target isEqualTo "hcs"): {
		[["HC"]] call _byKind
	};
	case (_target isEqualTo "interface"): {
		(keys brmh_machines) select {
			(brmh_machines get _x) getOrDefault ["iface", false]
		}
	};
	case (_target find "owner:" isEqualTo 0): {
		[parseNumber (_target select [6])]
	};
	case (_target find "player:" isEqualTo 0): {
		private _name = toLower (_target select [7]);
		(allPlayers select {
			(toLower name _x) isEqualTo _name
		}) apply {
			owner _x
		}
	};
	default {
		[]
	};
}
