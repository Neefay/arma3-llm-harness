/*
	NAME: task_eliminate
	DESCRIPTION: Give a side a task to kill a group, marked on its map, which completes by itself when the group is
		all dead. Each call makes a new task.
	PARAMETERS:
		0 - group (GROUP): the group to kill, such as a spawn_group handle
		1 - title (STRING, default "Clear the area"): the task's title
		2 - description (STRING, default "Eliminate the enemy."): its text
		3 - for (SIDE, default "west"): whose task
	RETURNS: the task's id (STRING)
	TARGET: server
	TAGS: task, objective, mission, kill, eliminate, briefing
	EXAMPLE: {"group": "player", "title": "Test task"}
*/
params ["_group", "_title", "_description", "_for"];
if (isNull _group) exitWith {
	"ERROR: no such group"
};
brmh_lib_tasks = (missionNamespace getVariable ["brmh_lib_tasks", 0]) + 1;
private _id = format ["agentTask%1", brmh_lib_tasks];
[_for, _id, [_description, _title, ""], getPosATL leader _group, "ASSIGNED", 1, true, "attack"] call BIS_fnc_taskCreate;
// A plain wait: one per task, checking every 2 s, and it ends with the task.
[_group, _id] spawn {
	params ["_group", "_id"];
	waitUntil {
		sleep 2;
		({
			alive _x
		} count units _group) isEqualTo 0
	};
	[_id, "SUCCEEDED"] call BIS_fnc_taskSetState;
};
_id
