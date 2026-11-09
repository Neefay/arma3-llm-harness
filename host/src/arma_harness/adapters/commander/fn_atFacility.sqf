// A medical vehicle or an aid post close enough to make a difference. ACE itself makes no treatment faster for being in one.
params ["_man"];
private _inside = vehicle _man;
if (_inside isNotEqualTo _man and {
	[_inside] call brmh_cmd_fnc_isMedicalVehicle
}) exitWith {
	true
};
(brmh_cmd_posts findIf {
	alive _x and {
		(_x distance2D _man) < 30
	}
}) >= 0 or {
	(((_man nearEntities [["Car", "Tank", "Air"], 15]) findIf {
		alive _x and {
			[_x] call brmh_cmd_fnc_isMedicalVehicle
		}
	}) >= 0)
}
