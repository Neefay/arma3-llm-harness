/*
	NAME: brmh_cmd_fnc_stepBuilds
	DESCRIPTION: Steps every machine in brmh_cmd_builds once, and keeps those still running. Called by
		brmh_cmd_fnc_step, every 2 s.
	PARAMETERS: None
	USAGE:
		call brmh_cmd_fnc_stepBuilds;
	RETURNS: Nothing
	ENVIRONMENT: Server, unscheduled
*/
brmh_cmd_builds = brmh_cmd_builds select {
	_x call ["#STEP", []]
};
