"""How does a vanilla bomb fly once released, for strikes without ACE? An A-164 drops on a level run over a grid,
and the bomb's position and velocity are recorded every frame until it explodes.

- mk82: Mk82s released at nothing. Is it ballistic, and what drag (a = g - k |v| v) fits it?
- laser: the vanilla GBU-12 released at a laser spot made just before and kept alive (BromA moves its spot every few
  seconds, as the engine deletes one nobody designates). Does the engine's own guidance take it to the grid?

    spike_bomb_drag.py [mk82|laser] [drops] [--save tracks.json] [--stop]
"""
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "move_lag"))
from spike_lib import in_fresh_game  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--") and not a.endswith(".json")]
mode = args[0] if args else "mk82"
drops = int(args[1]) if len(args) > 1 else 2
AIM = [3750, 2450]
MAGAZINE = {"mk82": "PylonMissile_1Rnd_Mk82_F", "laser": "PylonMissile_1Rnd_Bomb_04_F"}[mode]
harness, run = in_fresh_game("commander_stratis_ace")
run("""
{ deleteVehicle _x } forEach (missionNamespace getVariable ["spike_things", []]);
if (not isNil "spike_frameHandler") then { removeMissionEventHandler ["EachFrame", spike_frameHandler] };
spike_things = []; spike_tracks = []; spike_live = []; spike_impacts = [];
spike_frameHandler = addMissionEventHandler ["EachFrame", {
    { _x params ["_bomb", "_track"]; if (alive _bomb) then { _track pushBack [time, getPosASL _bomb, velocity _bomb] } }
        forEach spike_live;
}];
true
""")
weapon = run(f"""
private _pos = {AIM} getPos [6000, 225];
private _veh = createVehicle ["B_Plane_CAS_01_dynamicLoadout_F", _pos, [], 0, "FLY"];
_veh setPosASL [_pos # 0, _pos # 1, (getTerrainHeightASL _pos) + 800]; _veh setDir 45;
_veh setVelocityModelSpace [0, 120, 0];
createVehicleCrew _veh; _veh flyInHeight 800;
{{ if ("{MAGAZINE}" in (_veh getCompatiblePylonMagazines (_forEachIndex + 1))) then {{
    _veh setPylonLoadout [_forEachIndex + 1, "{MAGAZINE}", true] }} }} forEach getPylonMagazines _veh;
_veh addEventHandler ["Fired", {{
    params ["_veh", "_weapon", "_muzzle", "_mode", "_ammo", "_mag", "_projectile"];
    private _track = [[time, getPosASL _projectile, velocity _projectile]];
    spike_live pushBack [_projectile, _track];
    spike_tracks pushBack [_ammo, _track];
    _projectile addEventHandler ["Explode", {{
        params ["_projectile", "_pos"];
        spike_impacts pushBack [round time, typeOf _projectile, round (_pos distance2D ({AIM} + [0]))];
    }}];
}}];
spike_air = _veh; spike_grp = group driver _veh; spike_things append [_veh] + crew _veh;
(spike_grp addWaypoint [{AIM} + [0], 0]) setWaypointType "MOVE";
spike_grp setBehaviour "CARELESS"; spike_grp setCombatMode "BLUE";
getText (configFile >> "CfgMagazines" >> "{MAGAZINE}" >> "pylonWeapon")
""")
print("weapon", weapon, flush=True)
released, started = 0, time.time()
while released < drops and time.time() - started < 420:
    time.sleep(1)
    distance, off = run(f"""
    [round (spike_air distance2D ({AIM} + [0])), round (((spike_air getRelDir ({AIM} + [0])) + 180) mod 360 - 180)]
    """)
    if distance < 1000:
        run(f"""
        while {{count waypoints spike_grp > 0}} do {{ deleteWaypoint [spike_grp, 0] }};
        (spike_grp addWaypoint [{AIM} getPos [5000, 225], 0]) setWaypointType "MOVE";
        (spike_grp addWaypoint [{AIM} + [0], 0]) setWaypointType "MOVE"; true
        """)
        time.sleep(20)
        continue
    window = (1500, 2500) if mode == "laser" else (2000, 3200)
    if window[0] <= distance <= window[1] and abs(off) < 10:
        if mode == "laser":
            fired = run(f"""
            private _t = createVehicle ["LaserTargetW", {AIM} + [0], [], 0, "CAN_COLLIDE"];
            spike_things pushBack _t;
            [_t] spawn {{ params ["_t"]; for "_i" from 1 to 60 do {{ _t setPosATL ({AIM} + [0]); sleep 1 }} }};
            spike_air reveal [_t, 4];
            spike_air fireAtTarget [_t, "{weapon}"]
            """)
        else:
            fired = run(f'spike_air fireAtTarget [objNull, "{weapon}"]')
        print("release", distance, off, fired, flush=True)
        released += 1
        time.sleep(25)
time.sleep(30)
print("impacts", run("spike_impacts"))
G = 9.81
tracks = run("spike_tracks")
if "--save" in sys.argv:  # every frame of every bomb, for fitting a model offline
    import json
    out = Path(sys.argv[sys.argv.index("--save") + 1])
    out.write_text(json.dumps(tracks), encoding="utf-8")
    print("saved", out)
for ammo, track in tracks:
    first, end = track[0], track[-1]
    vx, vy, vz = first[2]
    print(ammo, "release speed", round(math.hypot(vx, vy)), "vz", round(vz, 1), "height ASL", round(first[1][2]),
          "flight", round(end[0] - first[0], 1), "s", "throw", round(math.dist(first[1][:2], end[1][:2])),
          "end vz", round(end[2][2], 1))
    ks = []
    for (t0, _p0, v0), (t1, _p1, v1) in zip(track, track[1:], strict=False):
        dt = t1 - t0
        speed = math.hypot(*v0)
        if dt <= 0.01 or speed < 1:
            continue
        a = [(v1[i] - v0[i]) / dt for i in range(3)]
        a[2] += G
        along = -sum(a[i] * v0[i] for i in range(3)) / speed  # the drag along the velocity: a_drag = -k |v| v
        ks.append(along / speed ** 2)
    ks.sort()
    if ks:
        print("   k median", f"{ks[len(ks) // 2]:.6f}", "quartiles", f"{ks[len(ks) // 4]:.6f}",
              f"{ks[3 * len(ks) // 4]:.6f}", "samples", len(ks))
print(harness.stop() if "--stop" in sys.argv else "game left up")
