/*
	NAME: spawn_animal
	DESCRIPTION: Spawn an animal, or any other agent, next to someone. Animals: Goat_random_F, Sheep_random_F,
		Fin_random_F (dog), Hen_random_F, Cock_random_F, Rabbit_F.
	PARAMETERS:
		0 - class (STRING, default "Goat_random_F"): the animal's class
		1 - near (OBJECT, default "player"): who it appears next to
		2 - distance (NUMBER, default 3): how far in front of them, in m
	RETURNS: handle (STRING)
	TARGET: server
	TAGS: spawn, animal, goat, dog, sheep, chicken, agent, create
	EXAMPLE: {"class": "Fin_random_F"}
*/
params ["_class", "_near", "_distance"];
if (not isClass (configFile >> "CfgVehicles" >> _class)) exitWith {
	format ["ERROR: there's no class %1", _class]
};
if (isNull _near) exitWith {
	"ERROR: no such unit to spawn it near"
};
private _agent = createAgent [_class, _near getPos [_distance, getDir _near], [], 0, "CAN_COLLIDE"];
[[_agent], _class] call brmh_lib_fnc_keep
