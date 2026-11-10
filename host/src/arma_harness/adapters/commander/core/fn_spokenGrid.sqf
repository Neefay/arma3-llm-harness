/*
	NAME: brmh_cmd_fnc_spokenGrid
	DESCRIPTION: A grid as it's said on the radio: "037024" becomes "037 024".
	PARAMETERS:
		0 - Grid, an even number of digits as mapGridPosition gives it (STRING)
	USAGE:
		private _said = [mapGridPosition _aim] call brmh_cmd_fnc_spokenGrid;
	RETURNS: The grid with its halves apart (STRING)
	ENVIRONMENT: Any machine, unscheduled or scheduled
*/
params ["_grid"];
private _half = (count _grid) / 2;
format ["%1 %2", _grid select [0, _half], _grid select [_half]]
