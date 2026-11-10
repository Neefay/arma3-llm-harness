params ["_man"];
private _key = _man getVariable ["brmh_cmd_man", ""];
if (_key isEqualTo "") then {
	brmh_cmd_manCount = brmh_cmd_manCount + 1;
	_key = format ["m%1", brmh_cmd_manCount];
	_man setVariable ["brmh_cmd_man", _key];
	brmh_cmd_men set [_key, _man];
};
_key
