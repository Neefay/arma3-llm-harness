// What the commander calls a magazine. Anything else a gun carries, such as mines or flares, isn't offered yet.
params ["_magazine"];
private _name = toLowerANSI _magazine;
if ("smoke" in _name) exitWith {
	"SMOKE"
};
if ("shells" in _name) exitWith {
	"HE"
};
""
