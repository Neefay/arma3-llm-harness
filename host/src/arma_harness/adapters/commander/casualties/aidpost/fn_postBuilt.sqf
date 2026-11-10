/*
	NAME: brmh_cmd_fnc_postBuilt
	DESCRIPTION: The aid post goes up 8 m in front of the medic: a real tent, which the engine can't damage. AI drivers
		don't avoid one, and a truck leaving a rendezvous flattened it through any damage handler. Shells hurt it by
		brmh_cmd_fnc_shellOnPosts. ACE counts it as a medical facility, and it gets a key like a vehicle's (P1, ...).
	PARAMETERS:
		0 - Aid post machine (HASHMAP object)
	USAGE:
		[_machine] call brmh_cmd_fnc_postBuilt;
	RETURNS: What "up" says: [its key, its grid] (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
params ["_machine"];
private _medic = _machine get "MEDIC";
private _tent = createVehicle ["Land_MedicalTent_01_MTP_closed_F", _medic getPos [8, getDir _medic], [], 6, "NONE"];
_tent setVariable ["brmh_cmd_spawned", true];
brmh_cmd_postCount = (missionNamespace getVariable ["brmh_cmd_postCount", 0]) + 1;
private _key = format ["P%1", brmh_cmd_postCount];
_tent setVariable ["brmh_cmd_key", _key];
_tent setVariable ["ace_medical_isMedicalFacility", true, true];
_tent allowDamage false;
brmh_cmd_vehicles set [_key, _tent];
brmh_cmd_posts pushBack _tent;
(_machine get "GROUP") setVariable ["brmh_cmd_post", _tent];
[_key, mapGridPosition _tent]
