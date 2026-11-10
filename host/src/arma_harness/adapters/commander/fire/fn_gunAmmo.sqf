/*
	NAME: brmh_cmd_fnc_gunAmmo
	DESCRIPTION: The rounds a gun has left, by the commander's word for them, over every magazine on its main turret.
		Magazines with no word, such as flares, are left out.
	PARAMETERS:
		0 - Gun (OBJECT)
	USAGE:
		[_gun] call brmh_cmd_fnc_gunAmmo; // [["HE", 14], ["SMOKE", 4]]
	RETURNS: [[word, rounds], ...], in no set order (ARRAY)
	ENVIRONMENT: Server, unscheduled
*/
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
