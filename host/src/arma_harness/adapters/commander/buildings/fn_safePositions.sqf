/*
	NAME: brmh_cmd_fnc_safePositions
	DESCRIPTION: A building's positions a soldier can be sent to without falling. On VR's cargo tower, men sent to the
		positions 13 to 18 m up fell off and broke their legs, five of eight in five minutes, and one died. The ones
		left out still count, so a building with any is reported checked, but not all of it: nobody has looked up there.
	PARAMETERS:
		0 - Building (OBJECT)
	USAGE:
		private _spots = [_building] call brmh_cmd_fnc_safePositions;
	RETURNS: Its positions no more than 10 m up, AGL (ARRAY)
	ENVIRONMENT: Any
*/
params ["_building"];
(_building buildingPos -1) select {
	(_x # 2) <= 10
}
