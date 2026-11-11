/*
	The command library's prelude, sent ahead of every command. It installs, once per machine and mission:
	- brmh_lib_fnc_object, _group, _position and _side, which turn what an assistant can say ("player", a name, a net
	  id, a grid, a "made:N" handle) into the engine's values;
	- brmh_lib_fnc_keep, which files what a command made under a handle, so delete_made can clean it up later.
	A reference that resolves to nothing gives objNull, grpNull or [] and the command reports it.
*/
if (isNil "brmh_lib_fnc_keep") then {
	brmh_lib_made = createHashMap;
	brmh_lib_next = 0;

	// Files things a command made: objects, groups, or markers' names. Returns the handle.
	brmh_lib_fnc_keep = {
		params [["_things", [], [[]]], ["_note", "", [""]]];
		brmh_lib_next = brmh_lib_next + 1;
		private _handle = format ["made:%1", brmh_lib_next];
		brmh_lib_made set [_handle, [_things, _note]];
		_handle
	};

	brmh_lib_fnc_object = {
		params ["_ref"];
		if (_ref isEqualType objNull) exitWith {
			_ref
		};
		if (_ref isEqualType grpNull) exitWith {
			leader _ref
		};
		if (not (_ref isEqualType "")) exitWith {
			objNull
		};
		private _key = toLowerANSI _ref;
		if (_key isEqualTo "player") exitWith {
			if (hasInterface and {not isNull player}) then {
				player
			} else {
				allPlayers param [0, objNull]
			}
		};
		if (_key find "made:" isEqualTo 0) exitWith {
			private _things = (brmh_lib_made getOrDefault [_key, [[], ""]]) # 0;
			private _first = _things param [0, objNull];
			if (_first isEqualType grpNull) then {
				leader _first
			} else {
				_first
			}
		};
		private _byNet = objectFromNetId _ref;
		if (not isNull _byNet) exitWith {
			_byNet
		};
		private _named = missionNamespace getVariable [_ref, objNull];
		if (_named isEqualType objNull and {not isNull _named}) exitWith {
			_named
		};
		private _people = (allPlayers + allUnits) select {
			toLowerANSI name _x isEqualTo _key
		};
		_people param [0, objNull]
	};

	brmh_lib_fnc_group = {
		params ["_ref"];
		if (_ref isEqualType grpNull) exitWith {
			_ref
		};
		if (_ref isEqualType "" and {(toLowerANSI _ref) find "made:" isEqualTo 0}) exitWith {
			private _things = (brmh_lib_made getOrDefault [toLowerANSI _ref, [[], ""]]) # 0;
			private _groups = _things select {
				_x isEqualType grpNull
			};
			if (_groups isNotEqualTo []) then {
				_groups # 0
			} else {
				group (_things param [0, objNull])
			}
		};
		if (_ref isEqualType "") then {
			private _byId = allGroups select {
				toLowerANSI groupId _x isEqualTo toLowerANSI _ref
			};
			if (_byId isNotEqualTo []) exitWith {
				_byId # 0
			};
			group ([_ref] call brmh_lib_fnc_object)
		} else {
			grpNull
		}
	};

	brmh_lib_fnc_position = {
		params ["_ref"];
		if (_ref isEqualType [] and {count _ref in [2, 3]}) exitWith {
			[_ref # 0, _ref # 1, _ref param [2, 0]]
		};
		if (not (_ref isEqualType "")) exitWith {
			[]
		};
		private _digits = (_ref splitString " ") joinString "";
		if (count _digits in [6, 8] and {(_digits regexMatch "[0-9]+")}) exitWith {
			// A grid of 100 m squares (6 figures) or 10 m (8): the centre of the square, checked against the map's own
			// grid, since some worlds don't number theirs this way.
			private _half = count _digits / 2;
			private _cell = [100, 10] select (_half isEqualTo 4);
			private _east = parseNumber (_digits select [0, _half]) * _cell + _cell / 2;
			private _north = parseNumber (_digits select [_half, _half]) * _cell + _cell / 2;
			if (_half isEqualTo 4 or {(mapGridPosition [_east, _north]) isEqualTo _digits}) then {
				[_east, _north, 0]
			} else {
				[]
			}
		};
		private _thing = [_ref] call brmh_lib_fnc_object;
		if (isNull _thing) then {
			[]
		} else {
			getPosATL _thing
		}
	};

	brmh_lib_fnc_side = {
		params ["_ref"];
		if (_ref isEqualType west) exitWith {
			_ref
		};
		switch (toLowerANSI _ref) do {
			case "east": {
				east
			};
			case "west": {
				west
			};
			case "civilian";
			case "civ": {
				civilian
			};
			default {
				independent
			};
		}
	};
};
