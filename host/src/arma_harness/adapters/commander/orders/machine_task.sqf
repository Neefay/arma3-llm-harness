// CBA's tasks handle the behaviour. They run until replaced, so the commander's next order has to undo them cleanly.
// A CBA task runs until the next order replaces it. Then the squad is released from it: CBA's scripts keep running,
// and DEFEND's disable each soldier's pathing as he reaches his post, so for 150 s his pathing is turned back on each
// step. Its state isn't said: the order that replaced it is.
brmh_cmd_taskMachine = [
	["KIND", "task"],
	["SAYS", false],
	["INITIAL", "running"],
	["STATES", [
		["running", [
			["ON", [
				[{
					_this getOrDefault ["REPLACED", false]
				}, {
					// ATTACK leaves a group crawling in COMBAT, and DEFEND at LIMITED speed. Both tested on a real game.
					(_this get "GROUP") setBehaviour "AWARE";
					(_this get "GROUP") setSpeedMode "NORMAL";
				}, "releasing", ""]
			]],
			["STANDING", true]
		]],
		["releasing", [
			["EVERY", {
				{
					_x enableAI "PATH";
				} forEach units (_this get "GROUP");
			}],
			["DEADLINE", [150, {}, "", ""]]
		]]
	]]
];
