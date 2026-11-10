"""A bomb on a grid with nobody there to see: the pilot flies a real run over the grid, and when he's pointed at it and
within range the script tells him to release on a laser spot there. Where does the bomb land?

    spike_release.py [weapon] [runs]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

weapon = sys.argv[1] if len(sys.argv) > 1 else "Bomb_04_Plane_CAS_01_F"
runs = int(sys.argv[2]) if len(sys.argv) > 2 else 2
AIM = [3750, 2450]
harness, run = in_fresh_game("commander_stratis")
run("""
{ deleteVehicle _x } forEach (missionNamespace getVariable ["spike_things", []]);
spike_things = []; spike_log = []; spike_impacts = []; true
""")
run(f"""
private _pos = [1500, 1500, 600];
private _veh = createVehicle ["B_Plane_CAS_01_dynamicLoadout_F", _pos, [], 0, "FLY"];
_veh setPosASL [1500, 1500, (getTerrainHeightASL _pos) + 600]; _veh setDir 45;
_veh setVelocityModelSpace [0, 110, 0];
createVehicleCrew _veh; _veh flyInHeight 400;
_veh addEventHandler ["Fired", {{
    params ["_veh", "_weapon", "_muzzle", "_mode", "_ammo", "_mag", "_projectile"];
    private _aim = ATLToASL ({AIM} + [0]);
    private _locked = [_projectile setMissileTargetPos _aim, not isNull spike_target];
    spike_log pushBack [round time, _ammo, round (_veh distance2D _aim), round ((getPosATL _veh) # 2), _locked];
    _projectile addEventHandler ["Explode", {{
        params ["_projectile", "_pos"];
        spike_impacts pushBack [round time, typeOf _projectile, round (_pos distance2D ({AIM} + [0]))];
    }}];
}}];
private _t = createVehicle ["LaserTargetW", {AIM} + [0], [], 0, "CAN_COLLIDE"];
spike_air = _veh; spike_grp = group driver _veh; spike_target = _t; spike_things append [_veh, _t] + crew _veh;
private _wp = spike_grp addWaypoint [{AIM} + [0], 0]; _wp setWaypointType "MOVE";
spike_grp setBehaviour "CARELESS"; spike_grp setCombatMode "BLUE";
true
""")
released, started = 0, time.time()
while released < runs and time.time() - started < 400:
    time.sleep(1)
    state = run(f"""
    private _to = spike_air getRelDir ({AIM} + [0]);
    private _off = (_to + 180) mod 360 - 180;
    private _d = spike_air distance2D ({AIM} + [0]);
    [round _d, round _off, round ((getPosATL spike_air) # 2), round speed spike_air]
    """)
    distance, off, height, speed = state
    if 1200 <= distance <= 2600 and abs(off) < 12:
        run(f'spike_air fireAtTarget [spike_target, "{weapon}"]')
        released += 1
        print("release at", state, flush=True)
        time.sleep(25)
        # Round again for the next run: away, then back over the grid.
        run(f"""
        while {{count waypoints spike_grp > 0}} do {{ deleteWaypoint [spike_grp, 0] }};
        (spike_grp addWaypoint [{AIM} getPos [3000, 225], 0]) setWaypointType "MOVE";
        (spike_grp addWaypoint [{AIM} + [0], 0]) setWaypointType "MOVE"; true
        """)
time.sleep(30)
print("fired", run("spike_log"))
print("impacts", run("spike_impacts"))
print(harness.stop() if "--stop" in sys.argv else "game left up")
