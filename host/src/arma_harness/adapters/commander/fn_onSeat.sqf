// A gun's crew only fires when ordered. A crewed gun otherwise opens up by itself at any enemy its crew knows of.
params ["_man", "_vehicle"];
if (getNumber (configOf _vehicle >> "artilleryScanner") > 0 and {
	gunner _vehicle isEqualTo _man
}) then {
	_man disableAI "TARGET";
	if (isNil {
		_man getVariable "brmh_cmd_offGunHandler"
	}) then {
		_man setVariable ["brmh_cmd_offGunHandler", _man addEventHandler ["GetOutMan", {
			params ["_unit"];
			_unit enableAI "TARGET";
		}]];
	};
};
