// Some of the last order's rounds have gone.
params ["_machine"];
private _mission = _machine get "MISSION";
(_mission getOrDefault ["fired", 0]) > (_mission get "firedAtIssue")
