/*
	NAME: brmh_cmd_fnc_kind
	DESCRIPTION: What a squad would call a contact, from the type it believes it is. The engine names the exact model as
		soon as it notices anything, so how much of that a squad can say is decided by how well it knows the target:
		see brmh_cmd_fnc_contacts.
	PARAMETERS:
		0 - Class name as believed, "" when not known (STRING)
	USAGE:
		private _kind = [typeOf _vehicle] call brmh_cmd_fnc_kind;
	RETURNS: "unknown", "infantry", "mortar", "emplacement", "tank", "tracked vehicle", "APC", "truck", "car",
		"armed car", "helicopter", "aircraft", "boat" or "vehicle" (STRING)
	ENVIRONMENT: Any
*/
params ["_type"];
private _config = configFile >> "CfgVehicles" >> _type;
switch (true) do {
	case (_type isEqualTo ""): {
		"unknown"
	};
	case (_type isKindOf "CAManBase"): {
		"infantry"
	};
	case (_type isKindOf "StaticMortar"): {
		"mortar"
	};
	case (_type isKindOf "StaticWeapon"): {
		"emplacement"
	};
	case (_type isKindOf "Tank"): {
		// A tracked carrier has room for troops. A tank doesn't.
		["tank", "tracked vehicle"] select (getNumber (_config >> "transportSoldier") > 0)
	};
	case (_type isKindOf "Wheeled_APC_F"): {
		"APC"
	};
	case (_type isKindOf "Truck_F"): {
		"truck"
	};
	case (_type isKindOf "Car"): {
		["car", "armed car"] select ((getArray (_config >> "Turrets" >> "MainTurret" >> "weapons")) isNotEqualTo [])
	};
	case (_type isKindOf "Helicopter"): {
		"helicopter"
	};
	case (_type isKindOf "Plane"): {
		"aircraft"
	};
	case (_type isKindOf "Ship"): {
		"boat"
	};
	case (_type isKindOf "LandVehicle"): {
		"vehicle"
	};
	default {
		"unknown"
	};
};
