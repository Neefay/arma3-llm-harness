/*
	NAME: brmh_cmd_fnc_machineProblems
	DESCRIPTION: What's wrong with a machine's declaration, as plain sentences: a state with no deadline, an ending
		with no word, a state that isn't declared. brmh_cmd_fnc_newMachine logs each as an error when it makes one.
	PARAMETERS:
		0 - The declaration as brmh_cmd_fnc_newMachine has turned it into, with STATES a hashmap of each state's own
		    hashmap (HASHMAP)
	USAGE:
		private _problems = [_spec] call brmh_cmd_fnc_machineProblems;
	RETURNS: The problems, empty when it's sound (ARRAY of STRING)
	ENVIRONMENT: Any machine, unscheduled or scheduled
*/
params ["_spec"];
private _states = _spec get "STATES";
private _problems = [];
if (not ((_spec getOrDefault ["INITIAL", ""]) in _states)) then {
	_problems pushBack "its initial state isn't declared";
};
private _says = _spec getOrDefault ["SAYS", true];
private _check = {
	params ["_where", "_transition"];
	_transition params ["", "", ["_next", ""], ["_word", ""]];
	if (_says and {
		_next isEqualTo ""
	} and {
		_word isEqualTo ""
	}) then {
		_problems pushBack format ["%1 can end without a word", _where];
	};
	if (_next isNotEqualTo "" and {
		not (_next in _states)
	}) then {
		_problems pushBack format ["%1 goes to %2, which isn't declared", _where, _next];
	};
};
{
	["ALWAYS", _x] call _check;
} forEach (_spec getOrDefault ["ALWAYS", []]);
{
	private _name = _x;
	switch (true) do {
		case ("DEADLINE" in _y): {
			[_name + " at its deadline", _y get "DEADLINE"] call _check;
		};
		case (not (_y getOrDefault ["STANDING", false])): {
			_problems pushBack format ["%1 waits with no deadline", _name];
		};
	};
	{
		[_name, _x] call _check;
	} forEach (_y getOrDefault ["ON", []]);
} forEach _states;
_problems
