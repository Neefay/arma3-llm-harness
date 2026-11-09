// Which of a squad are medics, from the end of its list. Operator action, from the scenario.
params [["_callsign", "", [""]], ["_count", 0, [0]]];
private _men = +(units (brmh_cmd_stations get _callsign));
reverse _men;
{
	_x setVariable ["ace_medical_medicClass", 1, true];
	_x setUnitTrait ["medic", true];
} forEach (_men select [0, _count]);
true
