/*
	NAME: brmh_cmd_fnc_isMedicalVehicle
	DESCRIPTION: Whether a vehicle is a medical one: ACE's flag on it if it's set, its config's attendant entry if not.
		ACE's own test, so it works with or without ACE.
	PARAMETERS:
		0 - Vehicle (OBJECT)
	USAGE:
		[vehicle _man] call brmh_cmd_fnc_isMedicalVehicle
	RETURNS: BOOL
	ENVIRONMENT: Any machine. Used on the server
*/
params ["_vehicle"];
_vehicle getVariable ["ace_medical_isMedicalVehicle", getNumber (configOf _vehicle >> "attendant") > 0]
