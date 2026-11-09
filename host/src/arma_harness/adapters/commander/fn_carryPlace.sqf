params ["_carry"];
private _to = _carry get "TO";
if (_to isEqualType objNull) then {
	getPosATL _to
} else {
	_to
}
