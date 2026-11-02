/*
	NAME: BRMH_fnc_sanitize
	DESCRIPTION: Converts any value into something toJSON represents faithfully: objects become
		{"$obj", "$type", "$netId"}, non-string hashmap keys are stringified, other engine types become
		"$TYPE:str" strings, NaN and infinities become "$num:..." strings.
	PARAMETERS:
		0 - Value (ANY)
		1 - (OPTIONAL) Current depth, internal (NUMBER) - Default: 0
	USAGE:
		[[player, west, {hint "x"}]] call BRMH_fnc_sanitize;
	RETURNS: JSON-safe value (ANY)
	ENVIRONMENT: Any machine
*/
params ["_value", ["_depth", 0]];

if (isNil "_value") exitWith {
	nil
};
if (_depth > 12) exitWith {
	"$depth"
};

switch (typeName _value) do {
	case "ARRAY": {
		_value apply {
			[_x, _depth + 1] call BRMH_fnc_sanitize
		}
	};
	case "HASHMAP": {
		private _out = createHashMap;
		{
			private _key = if (_x isEqualType "") then {
				_x
			} else {
				str _x
			};
			_out set [_key, [_y, _depth + 1] call BRMH_fnc_sanitize];
		} forEach _value;
		_out
	};
	case "OBJECT": {
		createHashMapFromArray [
			["$obj", str _value],
			["$type", typeOf _value],
			["$netId", netId _value]
		]
	};
	case "SCALAR": {
		if (finite _value) then {
			_value
		} else {
			format ["$num:%1", _value]
		}
	};
	case "NaN": {
		"$num:NaN"
	};
	case "BOOL";
	case "STRING": {
		_value
	};
	default {
		format ["$%1:%2", typeName _value, str _value]
	};
}
