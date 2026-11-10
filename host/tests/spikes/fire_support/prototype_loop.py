"""Prototype: one complete fire mission on a real game, outside the commander code. See docs/COMMANDER_FIRE_SUPPORT.md.

A squad mounts a real mortar. It's told to fire by grid reference, a spotter reports where rounds land relative to the
enemy it can see, the script corrects with a new 8-figure grid, and fires for effect. Then check fire, shots it can't make,
friendly fire and dismounting. The script plays the commander, and only ever uses what the radio text tells it.

    ..\\..\\..\\.venv\\Scripts\\python.exe prototype_loop.py
"""
from __future__ import annotations

import math
import re
import time

from spike_arty_lib import game, run, show

GUN = [1500.0, 1000.0]
ENEMY = [2120.0, 1730.0]  # about 960 m from the gun, deliberately not in the middle of a 100 m square
RECON = [2120.0, 1400.0]  # 330 m south of the enemy, in the open
FRIENDS = [1700.0, 1250.0]  # for the friendly fire step
results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail="") -> None:
    results.append((name, bool(passed), str(detail)))
    print(f"{'PASS' if passed else 'FAIL'}  {name}  {detail}", flush=True)


def grid6(x: float, y: float) -> str:
    return f"{int(x // 100):03d} {int(y // 100):03d}"


def grid8(x: float, y: float) -> str:
    return f"{int(x // 10):04d} {int(y // 10):04d}"


def parse_grid(text: str) -> list[float]:
    """6 figures mean the centre of a 100 m square, and 8 figures the centre of a 10 m one."""
    match = re.fullmatch(r"(\d{3})\s?(\d{3})|(\d{4})\s?(\d{4})", text.strip())
    if not match:
        raise ValueError(f"not a grid: {text}")
    if match[1]:
        return [int(match[1]) * 100 + 50.0, int(match[2]) * 100 + 50.0]
    return [int(match[3]) * 10 + 5.0, int(match[4]) * 10 + 5.0]


SETUP = """
params ["_gunAt", "_enemyAt", "_reconAt", "_friendsAt"];
brmh_p_shells = [];
brmh_p_kills = [];
private _listen = {
	_this addEventHandler ["Killed", {
		params ["_unit", "_killer", "_instigator"];
		brmh_p_kills pushBack [name _unit, str side group _unit, typeOf _killer, name _killer, isNull _instigator, getPosATL _unit, time];
	}];
};
private _squad = {
	params ["_at", "_side", "_class", "_count", "_listen"];
	private _group = createGroup [_side, false];
	for "_i" from 1 to _count do {
		private _man = _group createUnit [_class, _at + [0], [], 3, "NONE"];
		_man disableAI "PATH";
		_man call _listen;
	};
	_group setCombatMode "BLUE";
	_group
};
brmh_p_gun = createVehicle ["B_Mortar_01_F", _gunAt + [0], [], 0, "NONE"];
brmh_p_gun addEventHandler ["Fired", {
	params ["_gun", "", "", "", "_ammo", "", "_shell"];
	private _entry = createHashMapFromArray [["fired", time], ["ammo", _ammo]];
	brmh_p_shells pushBack _entry;
	_shell setVariable ["brmh_entry", _entry];
	_shell addEventHandler ["Explode", {
		params ["_shell", "_pos"];
		private _entry = _shell getVariable ["brmh_entry", createHashMap];
		_entry set ["landed", time];
		_entry set ["pos", _pos];
		_entry set ["seen", (units brmh_p_recon select {alive _x}) apply {
			[_x, "VIEW"] checkVisibility [eyePos _x, _pos vectorAdd [0, 0, 1]]
		}];
	}];
}];
brmh_p_hammer = createGroup [west, false];
for "_i" from 1 to 2 do { (brmh_p_hammer createUnit ["B_Soldier_F", _gunAt vectorAdd [40, 0, 0], [], 3, "NONE"]) call _listen; };
brmh_p_recon = [_reconAt, west, "B_recon_F", 2, _listen] call _squad;
brmh_p_enemy = [_enemyAt, east, "O_Soldier_F", 4, _listen] call _squad;
brmh_p_friends = [_friendsAt, west, "B_Soldier_F", 2, _listen] call _squad;
true
"""

# The battery's controller, in miniature: checks first, because each of these failures is otherwise silent.
FIRE = """
params ["_aim", "_magazine", "_rounds"];
private _gun = brmh_p_gun;
private _pos = _aim + [0];
private _man = gunner _gun;
if (not alive _gun) exitWith { "gun destroyed" };
if (isNull _man or {not alive _man}) exitWith { "no gunner" };
if (not (_magazine in getArtilleryAmmo [_gun])) exitWith { "no ammo" };
if (not (_pos inRangeOfArtillery [[_gun], _magazine])) exitWith { "out of range" };
brmh_p_mission = createHashMapFromArray [["start", count brmh_p_shells], ["want", _rounds], ["aim", _pos], ["mag", _magazine]];
_gun doWatch _pos;
_gun doArtilleryFire [_pos, _magazine, _rounds min 8];
["fired", _gun getArtilleryETA [_pos, _magazine]]
"""
STATUS = """
private _m = brmh_p_mission;
private _fired = (count brmh_p_shells) - (_m get "start");
private _gun = brmh_p_gun;
if (unitReady _gun and {_fired < (_m get "want")} and {_fired > 0} and {alive gunner _gun} and {_gun getVariable ["brmh_p_held", false] isEqualTo false}) then {
	_gun doArtilleryFire [_m get "aim", _m get "mag", ((_m get "want") - _fired) min 8];
};
private _shells = (brmh_p_shells select [_m get "start"]);
[_fired, unitReady _gun, if (isNull gunner _gun) then {""} else {currentCommand gunner _gun}, _shells apply {[_x getOrDefault ["pos", []], _x getOrDefault ["seen", []], _x get "fired", _x getOrDefault ["landed", -1]]}, count brmh_p_kills]
"""
PERCEIVED = """
private _leader = leader brmh_p_recon;
{ _leader reveal [_x, 4]; } forEach (units brmh_p_enemy select {alive _x});
sleep 0;
(units brmh_p_enemy select {alive _x}) apply {(_leader targetKnowledge _x) # 6}
"""


def seats(h) -> list:
    return run(h, 'fullCrew [brmh_p_gun, "", true] apply {[isNull (_x # 0), _x # 1, _x # 3]}')


def alive_counts(h) -> dict:
    return dict(zip(("enemy", "recon", "friends", "hammer"), run(h, """
    [brmh_p_enemy, brmh_p_recon, brmh_p_friends, brmh_p_hammer] apply {{alive _x} count units _x}
    """), strict=True))


def wait_mission(h, rounds: int, seconds: float = 90) -> list:
    """Until every round asked for has fired and landed, or the time's up."""
    deadline, status = time.time() + seconds, None
    while time.time() < deadline:
        status = run(h, STATUS)
        landed = [s for s in status[3] if s[0]]
        if status[0] >= rounds and len(landed) >= status[0]:
            return status
        time.sleep(2)
    return status


def spotter_report(impacts: list, seen: list, perceived: list) -> tuple[str, tuple[float, float] | None]:
    """What a spotter says: where the rounds fell against the enemy it can see, rounded, as words."""
    visible = [p for p, s in zip(impacts, seen, strict=True) if s and max(s) > 0.3]
    if not visible:
        return "Can't observe. No view of the fall of shot.", None
    x = sum(p[0] for p in visible) / len(visible)
    y = sum(p[1] for p in visible) / len(visible)
    tx = sum(p[0] for p in perceived) / len(perceived)
    ty = sum(p[1] for p in perceived) / len(perceived)
    east, north = round((x - tx) / 10) * 10, round((y - ty) / 10) * 10
    words = [f"{abs(north)} m {'north' if north >= 0 else 'south'}" if north else "", f"{abs(east)} m {'east' if east >= 0 else 'west'}" if east else ""]
    said = ", ".join(w for w in words if w) or "on"
    return f"Splash {said} of the enemy. {len(visible)} rounds seen.", (east, north)


def main() -> int:
    h = game()
    run(h, SETUP, [GUN, ENEMY, RECON, FRIENDS])
    time.sleep(4)

    # --- mounting by seat
    empty = seats(h)
    check("the gun lists its seats, and all are empty", empty == [[True, "gunner", [0]]], empty)
    run(h, """
    private _man = (units brmh_p_hammer) select {_x isNotEqualTo leader brmh_p_hammer} select 0;
    brmh_p_gunner = _man;
    _man assignAsGunner brmh_p_gun;
    [_man] orderGetIn true;
    true
    """)
    start = time.time()
    while time.time() < start + 60 and not run(h, "vehicle brmh_p_gunner isEqualTo brmh_p_gun"):
        time.sleep(1)
    took = round(time.time() - start)
    on_gun = run(h, "[gunner brmh_p_gun isEqualTo brmh_p_gunner, brmh_p_gunner isEqualTo leader brmh_p_hammer]")
    check("a subordinate mounts as gunner, not the leader", on_gun == [True, False], f"{took} s from 40 m")
    print(f"RADIO Hammer: Copy, mounting V1 as gunner. ... On V1 as gunner, {took} s later.", flush=True)

    # --- it mustn't fire by itself, even with an enemy it knows about
    run(h, """
    brmh_p_gunner disableAI "TARGET";
    { brmh_p_gunner reveal [_x, 4]; (leader brmh_p_hammer) reveal [_x, 4]; } forEach units brmh_p_enemy;
    true
    """)
    time.sleep(25)
    check("no self-firing in 25 s, at an enemy it knows of", run(h, "count brmh_p_shells") == 0, "disableAI TARGET")

    # --- shots it can't make are said aloud, not silently dropped
    far = run(h, FIRE, [[GUN[0] + 6000, GUN[1]], "8Rnd_82mm_Mo_shells", 2])
    near = run(h, FIRE, [[GUN[0] + 10, GUN[1]], "8Rnd_82mm_Mo_shells", 2])
    check("too far and too near are refused aloud", far == "out of range" and near == "out of range", (far, near))
    print("RADIO Hammer: Unable, out of range.", flush=True)

    # --- first rounds, by a 6-figure grid: the commander only knows roughly where the enemy is
    first_grid = grid6(*ENEMY)
    aim = parse_grid(first_grid)
    off = round(math.dist(aim, ENEMY))
    fired = run(h, FIRE, [aim, "8Rnd_82mm_Mo_shells", 2])
    check("a 6-figure mission fires", fired[0] == "fired", fired)
    print(f"RADIO HQ to Hammer: Fire mission, 2 HE, grid {first_grid}.  (aim is {off} m from the real enemy)", flush=True)
    print(f"RADIO Hammer: Shot, 2 rounds, splash in about {round(fired[1])} seconds.", flush=True)
    status = wait_mission(h, 2)
    impacts, seen = [s[0] for s in status[3]], [s[1] for s in status[3]]
    flight = [round(s[3] - s[2]) for s in status[3]]
    check("both rounds fired and landed, about when predicted", len(impacts) == 2 and abs(flight[0] - fired[1]) < 4, f"flight {flight}, predicted {round(fired[1])}")
    print("RADIO Hammer: Rounds complete.", flush=True)
    miss1 = round(sum(math.dist(p[:2], ENEMY) for p in impacts) / 2)

    # --- the spotter reports against the enemy it sees, and the commander works out a new grid
    perceived = run(h, PERCEIVED)
    words, offset = spotter_report(impacts, seen, perceived)
    print(f"RADIO Recon: {words}", flush=True)
    check("the spotter could see the fall of shot, and said where", offset is not None, seen)
    new_aim = [aim[0] - offset[0], aim[1] - offset[1]]
    second_grid = grid8(*new_aim)
    print(f"RADIO HQ to Hammer: Fire for effect, 6 HE, grid {second_grid}.  (worked out from the report)", flush=True)
    enemy_before = alive_counts(h)["enemy"]
    fired = run(h, FIRE, [parse_grid(second_grid), "8Rnd_82mm_Mo_shells", 6])
    status = wait_mission(h, 6)
    impacts = [s[0] for s in status[3]]
    miss2 = round(sum(math.dist(p[:2], ENEMY) for p in impacts) / max(1, len(impacts)))
    check("the correction landed closer", miss2 < miss1, f"mean miss {miss1} m, then {miss2} m")
    time.sleep(2)
    left = alive_counts(h)
    check("fire for effect hurt the enemy", left["enemy"] < enemy_before, f"enemy {enemy_before} to {left['enemy']}")
    check("fire for effect didn't touch Recon or the friendly squad", left["recon"] == 2 and left["friends"] == 2, left)

    # --- a mission across a magazine change
    run(h, FIRE, [[ENEMY[0], ENEMY[1] + 300], "8Rnd_82mm_Mo_shells", 10])
    status = wait_mission(h, 10, 70)
    check("10 rounds cross a magazine change", status[0] == 10, f"fired {status[0]}")

    # --- check fire
    run(h, FIRE, [[ENEMY[0], ENEMY[1] + 300], "8Rnd_82mm_Mo_shells", 8])
    start = time.time()
    while time.time() < start + 20 and run(h, STATUS)[0] < 2:
        time.sleep(0.3)
    fired_then = run(h, """
    doStop brmh_p_gun;
    brmh_p_gun setVariable ["brmh_p_held", true];
    (count brmh_p_shells) - (brmh_p_mission get "start")
    """)
    time.sleep(12)
    later = run(h, '(count brmh_p_shells) - (brmh_p_mission get "start")')
    check("check fire stops the gun at once", later == fired_then, f"{fired_then} fired when ordered, {later} 12 s later")
    print(f"RADIO Hammer: Check fire. {fired_then} rounds fired, some still in the air.", flush=True)
    run(h, 'brmh_p_gun setVariable ["brmh_p_held", false]; true')

    # --- friendly fire: nothing warns anyone, and the records can say whose shell it was
    before = run(h, "count brmh_p_kills")
    fired = run(h, FIRE, [FRIENDS, "8Rnd_82mm_Mo_shells", 6])
    check("nothing refuses a mission on friendlies", fired[0] == "fired", fired)
    status = wait_mission(h, 6)
    time.sleep(3)
    kills = run(h, f"brmh_p_kills select [{before}]")
    by_gun = [k for k in kills if k[2] == "B_Mortar_01_F"]
    friendly = [k for k in by_gun if "WEST" in k[1]]
    check("the deaths are recorded against the gun", bool(friendly), [(k[0], k[3], k[4]) for k in friendly])
    state = run(h, "[rating brmh_p_gunner, str side brmh_p_gunner, alive brmh_p_gunner, gunner brmh_p_gun isEqualTo brmh_p_gunner]")
    check("the gunner stays on the gun, and on our side", state[1:] == ["WEST", True, True], state)

    # --- getting off, and being able to fight again
    run(h, """
    brmh_p_gunner action ["GetOut", brmh_p_gun];
    unassignVehicle brmh_p_gunner;
    [brmh_p_gunner] orderGetIn false;
    brmh_p_gunner enableAI "TARGET";
    true
    """)
    time.sleep(10)
    off_gun = run(h, "[vehicle brmh_p_gunner isEqualTo brmh_p_gunner, brmh_p_gunner checkAIFeature 'TARGET', isNull gunner brmh_p_gun]")
    check("he gets off, with targeting back on", off_gun == [True, True, True], off_gun)
    show("ammo left", run(h, "magazinesAllTurrets brmh_p_gun apply {[_x # 0, _x # 2]}"))

    h.stop()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed} of {len(results)} passed", flush=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
