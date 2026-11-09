"""An ACE guided bomb on a bare grid, with nobody designating: which aircraft carry ACE's GBU-12 (laser) and SDB (GPS),
and where does a bomb land when the script releases it on a run over the grid?

- gbu: a virtual laser emitter, shining straight down on the grid (code 1111), registered with ace_laser_fnc_laserOn.
- sdb: ACE's GPS aim point (ace_missileguidance_gps_currentSettings) set to the grid on the server before release.

    spike_ace_bombs.py [gbu|sdb] [aircraft class] [runs] [--stop]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
kind = args[0] if args else "gbu"
plane = args[1] if len(args) > 1 else "B_Plane_CAS_01_dynamicLoadout_F"
runs = int(args[2]) if len(args) > 2 else 2
AIM = [3750, 2450]
harness, run = in_fresh_game("commander_stratis_ace")

print("ACE bombs by aircraft", run("""
["B_Plane_CAS_01_dynamicLoadout_F", "B_Plane_Fighter_01_F", "B_Heli_Attack_01_dynamicLoadout_F",
 "I_Plane_Fighter_04_F", "O_Plane_CAS_02_dynamicLoadout_F"] apply {
    private _cls = _x;
    private _all = [];
    { _all append (_cls getCompatiblePylonMagazines (_forEachIndex + 1)) } forEach
        ("true" configClasses (configFile >> "CfgVehicles" >> _cls >> "Components"
            >> "TransportPylonsComponent" >> "pylons"));
    _all = _all arrayIntersect _all;
    [_cls, _all select { "ace_missile" in toLowerANSI _x }]
}
"""))

run("""
{ deleteVehicle _x } forEach (missionNamespace getVariable ["spike_things", []]);
spike_things = []; spike_log = []; spike_impacts = []; true
""")
setup = run(f"""
private _kind = "{kind}";
private _pos = {AIM} getPos [6000, 225];
private _veh = createVehicle ["{plane}", _pos, [], 0, "FLY"];
_veh setPosASL [_pos # 0, _pos # 1, (getTerrainHeightASL _pos) + 800]; _veh setDir 45;
_veh setVelocityModelSpace [0, 120, 0];
createVehicleCrew _veh; _veh flyInHeight 800;
private _pylons = "true" configClasses (configFile >> "CfgVehicles" >> typeOf _veh >> "Components"
    >> "TransportPylonsComponent" >> "pylons");
private _want = ["ace_missile_gbu", "ace_missile_sdb"] select (_kind isEqualTo "sdb");
private _loaded = [];
{{
    private _mags = (_veh getCompatiblePylonMagazines (_forEachIndex + 1)) select {{ _want in toLowerANSI _x }};
    if (_mags isNotEqualTo []) then {{
        _veh setPylonLoadout [_forEachIndex + 1, _mags # 0, true];
        _loaded pushBack (_mags # 0);
    }};
}} forEach _pylons;
private _weapon = "";
{{
    private _ammo = getText (configFile >> "CfgMagazines" >> _x >> "ammo");
    if (_want in toLowerANSI _ammo) exitWith {{
        _weapon = getText (configFile >> "CfgMagazines" >> _x >> "pylonWeapon") }};
}} forEach _loaded;
spike_weapon = _weapon;
_veh addEventHandler ["Fired", {{
    params ["_veh", "_weapon", "_muzzle", "_mode", "_ammo", "_mag", "_projectile"];
    spike_log pushBack [round time, _ammo, round (_veh distance2D ({AIM} + [0])), round ((getPosATL _veh) # 2),
        round speed _veh];
    _projectile addEventHandler ["Explode", {{
        params ["_projectile", "_pos"];
        spike_impacts pushBack [round time, typeOf _projectile, round (_pos distance2D ({AIM} + [0]))];
    }}];
}}];
private _aimASL = AGLToASL ({AIM} + [0]);
if (_kind isEqualTo "sdb") then {{
    ace_missileguidance_gps_mode = "pb";
    ace_missileguidance_gps_currentSettings = [_aimASL, -1, -1];
}} else {{
    private _emitter = createVehicle ["Land_HelipadEmpty_F", {AIM} + [0], [], 0, "CAN_COLLIDE"];
    _emitter setVariable ["spike_aim", _aimASL];
    spike_laser = [_emitter, _emitter, {{
        params ["_obj"];
        private _aim = _obj getVariable "spike_aim";
        [_aim vectorAdd [0, 0, 150], [0, 0, -1]]
    }}, 1550, 1111, 1] call ace_laser_fnc_laserOn;
    spike_things pushBack _emitter;
}};
private _t = createVehicle ["LaserTargetW", {AIM} + [0], [], 0, "CAN_COLLIDE"];
spike_air = _veh; spike_grp = group driver _veh; spike_target = _t; spike_things append [_veh, _t] + crew _veh;
(spike_grp addWaypoint [{AIM} + [0], 0]) setWaypointType "MOVE";
spike_grp setBehaviour "CARELESS"; spike_grp setCombatMode "BLUE";
[_loaded, _weapon, _veh ammo _weapon]
""")
print("loaded", setup, flush=True)
if not setup[1]:
    print(harness.stop() if "--stop" in sys.argv else "game left up")
    sys.exit(f"{plane} takes no ACE {kind}")

released, started = 0, time.time()
while released < runs and time.time() - started < 420:
    time.sleep(1)
    state = run(f"""
    private _to = spike_air getRelDir ({AIM} + [0]);
    private _off = (_to + 180) mod 360 - 180;
    [round (spike_air distance2D ({AIM} + [0])), round _off, round ((getPosATL spike_air) # 2), round speed spike_air]
    """)
    distance, off, height, speed = state
    if distance < 1000:  # missed the window: round again
        print("passed without release", state, flush=True)
        run(f"""
        while {{count waypoints spike_grp > 0}} do {{ deleteWaypoint [spike_grp, 0] }};
        (spike_grp addWaypoint [{AIM} getPos [5000, 225], 0]) setWaypointType "MOVE";
        (spike_grp addWaypoint [{AIM} + [0], 0]) setWaypointType "MOVE"; true
        """)
        time.sleep(20)
        continue
    if 1500 <= distance <= 2500 and abs(off) < 15:
        print("release at", state, run("spike_air fireAtTarget [spike_target, spike_weapon]"), flush=True)
        released += 1
        time.sleep(30)
        run(f"""
        while {{count waypoints spike_grp > 0}} do {{ deleteWaypoint [spike_grp, 0] }};
        (spike_grp addWaypoint [{AIM} getPos [5000, 225], 0]) setWaypointType "MOVE";
        (spike_grp addWaypoint [{AIM} + [0], 0]) setWaypointType "MOVE"; true
        """)
time.sleep(30)
print("fired", run("spike_log"))
print("impacts", run("spike_impacts"))
print(harness.stop() if "--stop" in sys.argv else "game left up")
