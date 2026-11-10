// ATTACK, DEFEND, PATROL_AREA and SWEEP, which CBA's group tasks carry out. Made by brmh_cmd_fnc_startTask and
// stepped every 2 s in brmh_cmd_builds (brmh_cmd_fnc_stepBuilds). A CBA task runs until replaced, so the commander's
// next order has to undo it cleanly: brmh_cmd_fnc_order sets REPLACED, which moves "running" (standing) to
// "releasing". CBA's scripts keep running after that, and DEFEND's disable each soldier's pathing as he reaches his
// post, so for 150 s his pathing is turned back on each step, and then the machine ends. Its state isn't said: the
// order that replaced it is.
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
					// ATTACK leaves a group crawling in COMBAT, and DEFEND at LIMITED speed. Both tested on a real
					// game.
					(_this get "GROUP") setBehaviour "AWARE";
					(_this get "GROUP") setSpeedMode "NORMAL";
					// SWEEP's CBA_fnc_searchNearby locks the waypoints while it searches a building.
					(_this get "GROUP") lockWP false;
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
