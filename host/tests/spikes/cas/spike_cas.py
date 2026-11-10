"""What an AI aircraft really does when told to attack a grid, on Stratis. Read-only for the commander: this only spawns
aircraft and targets, watches them, and reports.

    spike_cas.py strike  B_Plane_CAS_01_dynamicLoadout_F  LaserTargetE
    spike_cas.py hunt    B_Heli_Attack_01_dynamicLoadout_F

strike: a laser spot on an empty grid, a DESTROY waypoint on it. Do bombs fall, and how close?
hunt:   enemies near a grid, a SAD waypoint there. Does the pilot find them by itself, and what does it hit?
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

mode = sys.argv[1] if len(sys.argv) > 1 else "strike"
cls = sys.argv[2] if len(sys.argv) > 2 else "B_Plane_CAS_01_dynamicLoadout_F"
laser = sys.argv[3] if len(sys.argv) > 3 else "LaserTargetE"
watch_s = int(sys.argv[4]) if len(sys.argv) > 4 else 240
AIM = [3750, 2450]  # open ground east of Agios Ioannis, grid 037 024
HOLD = [2000, 1500]

harness, run = in_fresh_game("commander_stratis")
run("""
{ deleteVehicle _x } forEach (missionNamespace getVariable ["spike_things", []]);
{ deleteVehicle _x } forEach allDead;
spike_things = []; spike_log = []; spike_impacts = []; true
""")
print("aircraft", run(f"""
private _air = "{cls}" isKindOf "Plane";
private _pos = [{HOLD[0]}, {HOLD[1]}, [150, 500] select _air];
private _veh = createVehicle ["{cls}", _pos, [], 0, "FLY"];
_veh setPosASL [_pos # 0, _pos # 1, (getTerrainHeightASL _pos) + (_pos # 2)];
_veh setDir 45;
_veh setVelocityModelSpace [0, [40, 110] select _air, 0];
createVehicleCrew _veh;
private _grp = group driver _veh;
_veh flyInHeight ([100, 400] select _air);
private _wp = _grp addWaypoint [_pos, 0];
_wp setWaypointType "LOITER"; _wp setWaypointLoiterRadius ([400, 1200] select _air);
_wp setWaypointLoiterType "CIRCLE_L";
_veh addEventHandler ["Fired", {{
    params ["_veh", "_weapon", "_muzzle", "_mode", "_ammo", "_mag", "_projectile"];
    spike_log pushBack [round time, _weapon, _ammo];
    _projectile addEventHandler ["Explode", {{
        params ["_projectile", "_pos"];
        spike_impacts pushBack [round time, typeOf _projectile, round (_pos distance2D {AIM} + [0])];
    }}];
}}];
spike_air = _veh; spike_grp = _grp; spike_things pushBack _veh; spike_things append crew _veh;
[typeOf _veh, getPylonMagazines _veh, weapons _veh, round ((getPosATL _veh) # 2), count crew _veh,
 ("true" configClasses (configOf _veh >> "Components" >> "SensorsManagerComponent" >> "Components"))
     apply {{configName _x}}]
"""))
time.sleep(20)
print("loitering", run("[getPosATL spike_air apply {round _x}, round speed spike_air, "
                       "currentCommand driver spike_air]"))

if mode == "strike":
    print("strike", run(f"""
    private _t = createVehicle ["{laser}", {AIM} + [0], [], 0, "CAN_COLLIDE"];
    spike_things pushBack _t; spike_target = _t;
    spike_grp reveal [_t, 4];
    west reportRemoteTarget [_t, 3600];
    _t confirmSensorTarget [west, true];
    spike_air doTarget _t; spike_air doFire _t;
    while {{count waypoints spike_grp > 0}} do {{ deleteWaypoint [spike_grp, 0] }};
    private _wp = spike_grp addWaypoint [{AIM} + [0], 0];
    _wp setWaypointType "DESTROY"; _wp waypointAttachVehicle _t;
    spike_grp setCombatMode "RED"; spike_grp setBehaviour "COMBAT";
    [typeOf _t, side _t, (driver spike_air) knowsAbout _t]
    """))
else:
    print("enemies", run(f"""
    private _e = createGroup [east, true];
    for "_i" from 1 to 4 do {{ _e createUnit ["O_Soldier_F", {AIM} getPos [random 40, random 360], [], 0, "NONE"] }};
    private _car = createVehicle ["O_MRAP_02_hmg_F", {AIM} getPos [60, 90], [], 0, "NONE"];
    createVehicleCrew _car;
    spike_things append (units _e) + [_car] + crew _car;
    spike_enemies = (units _e) + [_car] + crew _car;
    while {{count waypoints spike_grp > 0}} do {{ deleteWaypoint [spike_grp, 0] }};
    private _wp = spike_grp addWaypoint [{AIM} + [0], 0];
    _wp setWaypointType "SAD"; spike_grp setCombatMode "RED"; spike_grp setBehaviour "COMBAT";
    count spike_enemies
    """))

started = time.time()
while time.time() - started < watch_s:
    time.sleep(15)
    print(round(time.time() - started), run(f"""
    private _known = if (isNil "spike_enemies") then {{ [] }} else {{
        spike_enemies select {{ (driver spike_air) knowsAbout _x > 1 }} }};
    [alive spike_air, round (spike_air distance2D ({AIM} + [0])), round ((getPosATL spike_air) # 2),
     round speed spike_air, currentCommand driver spike_air, count spike_log,
     spike_impacts select [0 max (count spike_impacts - 4)],
     if (isNil "spike_enemies") then {{ "" }} else {{ [count _known, {{ alive _x }} count spike_enemies] }}]
    """), flush=True)
print("fired", run("spike_log"))
print("impacts", run("spike_impacts"))
print("ammo left", run("magazinesAllTurrets spike_air apply { [_x # 0, _x # 2] }"))
print(harness.stop() if "--stop" in sys.argv else "game left up")
