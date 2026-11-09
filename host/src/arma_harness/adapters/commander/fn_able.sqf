// Who can do anything. Under ACE a downed man is alive, and stays in his group, lying where he fell.
params ["_man"];
alive _man and {
	lifeState _man isNotEqualTo "INCAPACITATED"
}
