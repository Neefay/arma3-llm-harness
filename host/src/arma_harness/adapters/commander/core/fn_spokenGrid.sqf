// "037024" as it's said on the radio, "037 024".
params ["_grid"];
private _half = (count _grid) / 2;
format ["%1 %2", _grid select [0, _half], _grid select [_half]]
