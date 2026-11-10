// Close air support: the pilot flies to the grid and attacks whatever he finds there himself, by the engine's own
// seek-and-destroy. Nothing is aimed for him: no AI aircraft will bomb a bare grid (docs/COMMANDER_CAS.md).
brmh_cmd_sortieMachine = [
	["KIND", "sortie"],
	["INITIAL", "inbound"],
	["ALWAYS", [
		[{
			not alive (_this get "VEHICLE") or {
				not ([driver (_this get "VEHICLE")] call brmh_cmd_fnc_able)
			}
		}, {}, "", "lost"],
		[{
			[_this get "VEHICLE"] call brmh_cmd_fnc_winchester
		}, {}, "", "winchester"]
	]],
	["STATES", [
		["inbound", [
			["ON", [
				[{
					((_this get "VEHICLE") distance2D (_this get "AIM")) <= (_this get "RADIUS") + 300
				}, {
					_this get "GRID"
				}, "over", "over"]
			]],
			["DEADLINE", [600, {}, "leaving", ""]]
		]],
		["over", [
			["EVERY", {
				[_this] call brmh_cmd_fnc_sortieSearch
			}],
			["ON", [
				[{
					[_this] call brmh_cmd_fnc_sortieShots > 0
				}, {
					((_this get "VEHICLE") getVariable ["brmh_cmd_lastShot", [0, "guns"]]) # 1
				}, "engaging", "engaging"],
				[{
					[_this] call brmh_cmd_fnc_sortieDone
				}, {}, "leaving", ""]
			]],
			["DEADLINE", [240, {}, "leaving", ""]]
		]],
		["engaging", [
			["EVERY", {
				[_this] call brmh_cmd_fnc_sortieSearch
			}],
			["ON", [
				[{
					[_this] call brmh_cmd_fnc_sortieDone
				}, {}, "leaving", ""]
			]],
			["DEADLINE", [240, {}, "leaving", ""]]
		]],
		["leaving", [
			["ON", [
				[{
					[_this] call brmh_cmd_fnc_sortieShots > 0
				}, {}, "", "off target"],
				[{
					true
				}, {
					_this get "GRID"
				}, "", "nothing seen"]
			]],
			["DEADLINE", [1, {}, "", "nothing seen"]]
		]]
	]],
	["RELEASE", {
		private _group = _this get "GROUP";
		if (alive (_this get "VEHICLE")) then {
			[_group, _group getVariable ["brmh_cmd_hold", getPosATL (_this get "VEHICLE")]] call brmh_cmd_fnc_holdAir;
		};
	}]
];
