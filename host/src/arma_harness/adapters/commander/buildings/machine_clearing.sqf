// CLEAR: the squad goes through the buildings one at a time, every position of each, and holds there when it's done.
// Its state reaches the host in the packet's "clearing" (positions left: -1 none, 0 done), "cleared", "ruined" and
// "blocked", which stay as they are until the next order.
brmh_cmd_clearingMachine = [
	["KIND", "clearing"],
	["SAYS", false],
	["INITIAL", "between"],
	["STATES", [
		["between", [
			["ON", [
				[{
					(_this get "QUEUE") isEqualTo []
				}, {
					{
						_x doFollow leader (_this get "GROUP");
					} forEach units (_this get "GROUP");
				}, "done", ""],
				[{
					isNull ([(_this get "QUEUE") # 0 # 1] call brmh_cmd_fnc_building)
				}, {
					(_this get "RUINED") pushBack (((_this get "QUEUE") deleteAt 0) # 0);
				}, "between", ""],
				[{
					true
				}, {
					[_this] call brmh_cmd_fnc_clearNext
				}, "inside", ""]
			]],
			["DEADLINE", [1, {}, "done", ""]]
		]],
		["inside", [
			["EVERY", {
				[_this] call brmh_cmd_fnc_stepClearing
			}],
			["ON", [
				[{
					(_this get "SPOTS") isEqualTo [] and {
						(_this get "BUSY") isEqualTo 0
					}
				}, {
					[_this] call brmh_cmd_fnc_clearDone
				}, "between", ""]
			]],
			// Each man has his own deadline for a position, so this is only a backstop.
			["DEADLINE", [600, {
				[_this] call brmh_cmd_fnc_clearDone
			}, "between", ""]]
		]],
		["done", [
			["STANDING", true]
		]]
	]]
];
