params ["_gun"];
private _counts = createHashMap;
{
	if ((_x # 1) isEqualTo [0]) then {
		private _word = [_x # 0] call brmh_cmd_fnc_ammoWord;
		if (_word isNotEqualTo "") then {
			_counts set [_word, (_counts getOrDefault [_word, 0]) + (_x # 2)];
		};
	};
} forEach magazinesAllTurrets _gun;
_counts toArray false
