/*
	NAME: brmh_cmd_fnc_isMedic
	DESCRIPTION: Whether a man is a medic: ACE's medic class if it's set, the engine's medic trait if not. ACE's own
		test without its boost for being in a medical vehicle or facility, so it works with or without ACE.
	PARAMETERS:
		0 - Man (OBJECT)
	USAGE:
		private _medics = (units _group) select {[_x] call brmh_cmd_fnc_isMedic};
	RETURNS: BOOL
	ENVIRONMENT: Any machine. Used on the server
*/
params ["_man"];
(_man getVariable ["ace_medical_medicClass", parseNumber (_man getUnitTrait "medic")]) > 0
