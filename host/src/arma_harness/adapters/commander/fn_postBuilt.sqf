// A real tent, which the engine can't damage: AI drivers don't avoid one, and a truck leaving a rendezvous flattened it
// through any damage handler. Shells hurt it by brmh_cmd_fnc_shellOnPosts. Returns what "up" says: its id and grid.
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
