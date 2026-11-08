/*
	The observer watches the battle and can't affect it: no weapons, can't be hurt, ignored by the AI.
	Starts in a free spectator camera, with the map on M. Radio traffic appears in chat and the commander's
	markers on the map. None of it reaches the commander.
*/
player allowDamage false;
player setCaptive true;
removeAllWeapons player;
removeAllItems player;
player linkItem "ItemMap";

// Spawned: the spectator needs the mission display, which doesn't exist yet at this point.
[] spawn {
	waitUntil {
		not isNull findDisplay 46
	};
	sleep 1;
	["Initialize", [player, [], true, true, true, true, true, true, true, true]] call BIS_fnc_EGSpectator;
};
