"""A squad firing a mortar reported a contact with no enemy on the map, at a bearing pointing at the map's origin.
What is it? Logs what the squad's leader believes for as long as it lasts, with a stretch of plain waiting first."""
import time

from spike_arty_lib import AREA, game, run, show

SETUP = """
params ["_at"];
private _gun = createVehicle ["B_Mortar_01_F", _at + [0], [], 0, "NONE"];
private _group = createGroup [west, false];
private _boss = _group createUnit ["B_Soldier_F", (_at vectorAdd [8, 0]) + [0], [], 0, "NONE"];
private _crew = _group createUnit ["B_Soldier_F", (_at vectorAdd [6, 0]) + [0], [], 0, "NONE"];
_group selectLeader _boss;
_crew moveInGunner _gun;
_crew disableAI "TARGET";
missionNamespace setVariable ["ghost_gun", _gun];
missionNamespace setVariable ["ghost_boss", _boss];
true
"""

LOOK = """
private _boss = missionNamespace getVariable "ghost_boss";
private _near = (_boss nearTargets 8000) apply {
	[_x # 0, _x # 1, str (_x # 2), typeOf (_x # 4), str (_x # 4), _x # 5]
};
private _enemy = (_boss targets [true, 2000]) apply {
	[typeOf _x, str _x, side _x, getPosATL _x, alive _x, isNull _x, _boss targetKnowledge _x]
};
private _any = (_boss targets [false, 8000]) apply {
	[typeOf _x, str _x, side _x, getPosATL _x]
};
[time, _enemy, _any, _near, getSuppression _boss, behaviour _boss, side _boss, rating gunner (missionNamespace getVariable "ghost_gun")]
"""

harness = game()
run(harness, SETUP, [AREA])
for i in range(4):
    time.sleep(3)
    show(f"before {i}", run(harness, LOOK))
at = [AREA[0] + 800, AREA[1]]
run(harness, '(missionNamespace getVariable "ghost_gun") doArtilleryFire [_this + [0], "8Rnd_82mm_Mo_shells", 2]; true', at)
for i in range(14):
    time.sleep(3)
    show(f"after {i}", run(harness, LOOK))
harness.stop()
