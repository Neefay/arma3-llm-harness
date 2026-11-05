/*
	The VR map is empty: build a small village for commander scenarios to fight over, around grid 041 041.
	Every object is checked with isClass, so a missing class is skipped rather than breaking the mission.
*/
private _layout = [
	// [class, [x, y], direction]
	["Land_i_House_Big_02_V2_F", [4060, 4150], 180],
	["Land_i_House_Big_01_V3_F", [4110, 4160], 200],
	["Land_i_Stone_HouseBig_V2_F", [4150, 4130], 250],
	["Land_i_House_Small_02_V3_F", [4030, 4120], 120],
	["Land_u_Shop_02_V1_F", [4095, 4205], 180],
	["Land_i_House_Small_01_V3_F", [4170, 4190], 220],
	["Land_Cargo_Tower_V1_F", [4000, 4210], 160],
	["Land_LampStreet_F", [4085, 4130], 0],
	["Land_LampStreet_F", [4125, 4180], 0],
	["C_Offroad_01_F", [4080, 4170], 90],
	["C_Hatchback_01_F", [4135, 4150], 30]
];
{
	_x params ["_class", "_pos", "_dir"];
	if (isClass (configFile >> "CfgVehicles" >> _class)) then {
		private _object = createVehicle [_class, _pos + [0], [], 0, "CAN_COLLIDE"];
		_object setDir _dir;
		_object setPosATL (_pos + [0]);
	};
} forEach _layout;
