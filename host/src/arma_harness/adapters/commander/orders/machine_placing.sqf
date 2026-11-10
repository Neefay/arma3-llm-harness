// OCCUPY and CORDON: each soldier gets a spot and walks there, and the squad holds when they all have, or after 90 s.
// Its state reaches the host as the packet's "placed": -1 none, 0 moving, 1 placed.
brmh_cmd_placingMachine = [
	["KIND", "placing"],
	["SAYS", false],
	["INITIAL", "moving"],
	["STATES", [
		["moving", [
			["ON", [
				[{
					({
						not unitReady _x
					} count ([_this get "GROUP"] call brmh_cmd_fnc_freeMen)) isEqualTo 0
				}, {
					[_this] call brmh_cmd_fnc_settlePlacing
				}, "placed", ""]
			]],
			["DEADLINE", [90, {
				[_this] call brmh_cmd_fnc_settlePlacing
			}, "placed", ""]]
		]],
		["placed", [
			["STANDING", true]
		]]
	]]
];
