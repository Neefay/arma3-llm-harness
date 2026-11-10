/*
	NAME: brmh_cmd_fnc_atFacility
	DESCRIPTION: Whether a man is somewhere that makes his care faster: aboard a medical vehicle, within 15 m of one,
		or within 30 m of a standing aid post. ACE itself makes no treatment faster for being in one: the times in
		brmh_cmd_careTimes do.
	PARAMETERS:
		0 - Man (OBJECT)
	USAGE:
		private _fast = [_man] call brmh_cmd_fnc_atFacility;
	RETURNS: Whether he's at one (BOOL)
	ENVIRONMENT: Server, unscheduled
*/
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
