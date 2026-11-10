// A numbered building, if it's still standing. A destroyed one becomes a ruin that isn't a House. The search has to be wide,
// because it measures in 3D from the model's centre, which is high up on a tower, but only what's directly here counts,
// or it would find a neighbour instead.
params ["_pos"];
private _here = (_pos select [0, 2]) + [0];
private _found = (nearestObjects [_here, ["House"], 40]) select {
	alive _x and {
		(_x distance2D _here) < 6
	} and {
		(_x buildingPos -1) isNotEqualTo []
	}
};
if (_found isEqualTo []) then {
	objNull
} else {
	_found # 0
}
