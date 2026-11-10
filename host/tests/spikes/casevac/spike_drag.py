"""Can an AI move a casualty? On a dedicated server, with ACE.

A: ACE's own carry, called directly, then an ordinary doMove.
B: Antistasi's drag: the medic and casualty are attached to a hidden dummy that does the walking.
C: A plain attach: casualty on the medic's shoulder, and the medic walks as normal.
D: The owner's fallback: walk to the body, long animation, loadPerson into a vehicle. Then drive, unload, heal in a tent.
E: A leader goes down. Does the squad still obey?
G: ACE's own AI medic, on a wounded man in his group, with no enemy around.
"""
import time

from spike_ace_lib import game, run, show

SETUP = """
missionNamespace setVariable ["ace_medical_spontaneousWakeUpChance", 0, true];
brmh_fnc_squad = {
    params ["_at", ["_optOut", true]];
    private _group = createGroup [west, false];
    private _boss = _group createUnit ["B_Soldier_F", _at vectorAdd [0, 8, 0], [], 0, "CAN_COLLIDE"];
    private _medic = _group createUnit ["B_medic_F", _at vectorAdd [3, 0, 0], [], 0, "CAN_COLLIDE"];
    private _hurt = _group createUnit ["B_Soldier_F", _at, [], 0, "CAN_COLLIDE"];
    _group selectLeader _boss;
    if (_optOut) then {
        {
            _x setVariable ["ace_medical_ai_lastFired", CBA_missionTime + 86400];
        } forEach [_boss, _medic, _hurt];
    };
    [_boss, _medic, _hurt]
};
brmh_fnc_row = {
    params ["_squad", "_from"];
    _squad params ["_boss", "_medic", "_hurt"];
    [
        round (_medic distance2D _from), round (_hurt distance2D _from), round (_medic distance2D _hurt),
        alive _hurt, _hurt getVariable ["ACE_isUnconscious", false], lifeState _hurt,
        str (attachedTo _hurt), animationState _medic, animationState _hurt,
        typeOf (vehicle _hurt), group _hurt isEqualTo group _medic, round (speed _medic), behaviour _medic,
        leader group _boss isEqualTo _boss
    ]
};
true
"""


def trace(harness, name, seconds, step=5):
    print(f"  [medic from start, body from start, medic to body, alive, uncon, lifeState, attachedTo, medic anim, "
          f"body anim, body vehicle, same group, speed, behaviour, boss leads]", flush=True)
    for _ in range(seconds // step):
        show(f"  {name}", run(harness, f"[{name}, {name}_from] call brmh_fnc_row"))
        time.sleep(step)


def section(title):
    print(f"\n=== {title}", flush=True)


def attempt(harness, label, code):
    try:
        show(label, run(harness, code))
    except RuntimeError as error:
        print(f"{label} FAILED: {str(error)[:900]}", flush=True)


harness = game()
run(harness, SETUP)

section("A: ACE carry, called directly, then doMove")
run(harness, """
brmh_a_from = [1500, 1500, 0];
brmh_a = [brmh_a_from] call brmh_fnc_squad;
[brmh_a # 2, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
time.sleep(4)
attempt(harness, "claim", "[brmh_a # 1, brmh_a # 2, true] call ace_common_fnc_claimSafeServer; true")
attempt(harness, "carry", "[brmh_a # 1, brmh_a # 2, true] call ace_dragging_fnc_startCarryLocal; true")
trace(harness, "brmh_a", 14, 7)
run(harness, "(brmh_a # 1) doMove [1580, 1500, 0]; true")
trace(harness, "brmh_a", 30)

section("B: Antistasi's drag, with a dummy doing the walking")
run(harness, """
brmh_b_from = [1500, 1800, 0];
brmh_b = [brmh_b_from] call brmh_fnc_squad;
[brmh_b # 2, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
time.sleep(4)
run(harness, """
brmh_b spawn {
    params ["", "_medic", "_target"];
    _medic setUnitPos "MIDDLE";
    _medic playAction "grabDrag";
    private _out = time + 5;
    waitUntil {
        sleep 0.3;
        animationState _medic isEqualTo "amovpercmstpslowwrfldnon_acinpknlmwlkslowwrfldb_2" or {time > _out}
    };
    _target switchMove "AinjPpneMrunSnonWnonDb";
    _medic disableAI "ANIM";
    private _group = createGroup [civilian, true];
    private _dummy = _group createUnit ["C_man_polo_1_F", [0, 0, 20], [], 0, "FORM"];
    _dummy setUnitPos "MIDDLE";
    _dummy forceWalk true;
    _dummy switchMove "AmovPknlMstpSlowWnonDnon";
    hideObjectGlobal _dummy;
    _dummy allowDamage false;
    _dummy setBehaviour "CARELESS";
    _dummy disableAI "FSM";
    _dummy disableAI "SUPPRESSION";
    _dummy setPosATL (getPosATL _medic);
    _medic attachTo [_dummy, [0, -0.2, 0]];
    _medic setDir 180;
    _target attachTo [_dummy, [0, -1.1, 0.092]];
    _target setDir 0;
    _dummy doMove [1540, 1800, 0];
    brmh_b_dummy = _dummy;
    sleep 1;
    _medic playMove "AcinPknlMwlkSrasWrflDb";
};
true
""")
trace(harness, "brmh_b", 40)
attempt(harness, "dummy", "[unitReady brmh_b_dummy, round (brmh_b_dummy distance2D brmh_b_from), speed brmh_b_dummy]")
attempt(harness, "release", """
detach (brmh_b # 2); detach (brmh_b # 1); deleteVehicle brmh_b_dummy;
(brmh_b # 1) enableAI "ANIM"; (brmh_b # 1) playAction "released";
(brmh_b # 2) switchMove "UnconsciousReviveDefault";
true
""")
trace(harness, "brmh_b", 6, 3)

section("C: plain attach, and the medic walks as normal")
run(harness, """
brmh_c_from = [1500, 2100, 0];
brmh_c = [brmh_c_from] call brmh_fnc_squad;
[brmh_c # 2, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
time.sleep(4)
run(harness, """
private _medic = brmh_c # 1;
private _hurt = brmh_c # 2;
_hurt attachTo [_medic, [0.4, -0.1, -1.25], "LeftShoulder"];
_hurt setDir 195;
_hurt switchMove "AinjPfalMstpSnonWnonDf_carried_dead";
_medic doMove [1580, 2100, 0];
true
""")
trace(harness, "brmh_c", 30)

section("D: the fallback: walk to the body, long animation, load")
run(harness, """
brmh_d_from = [1500, 2400, 0];
brmh_d = [brmh_d_from] call brmh_fnc_squad;
(brmh_d # 1) setPosATL [1530, 2400, 0];
brmh_d_hunter = createVehicle ["B_MRAP_01_F", [1500, 2412, 0], [], 0, "CAN_COLLIDE"];
[brmh_d # 2, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
time.sleep(4)
started = time.time()
run(harness, "(brmh_d # 1) forceSpeed -1; (brmh_d # 1) doMove (getPosATL (brmh_d # 2)); true")
reached = None
for _ in range(30):
    away, ready = run(harness, "[(brmh_d # 1) distance2D (brmh_d # 2), unitReady (brmh_d # 1)]")
    if away <= 2.5 or ready:
        reached = round(time.time() - started)
        print(f"  reached in {reached} s, {away:.1f} m away, unitReady {ready}", flush=True)
        break
    time.sleep(2)
run(harness, """
(brmh_d # 1) playMoveNow "AinvPknlMstpSlayWrflDnon_medicOther";
true
""")
trace(harness, "brmh_d", 8, 4)
attempt(harness, "load", "[[brmh_d # 1, brmh_d # 2, brmh_d_hunter] call ace_common_fnc_loadPerson, true]")
trace(harness, "brmh_d", 6, 3)
attempt(harness, "crew", "crew brmh_d_hunter apply {[name _x, assignedVehicleRole _x, lifeState _x]}")
print("  driving", flush=True)
run(harness, """
(brmh_d # 0) moveInDriver brmh_d_hunter;
brmh_d_hunter doMove [1500, 2600, 0];
true
""")
time.sleep(25)
attempt(harness, "after driving", """
[round (brmh_d_hunter distance2D [1500, 2600, 0]), typeOf vehicle (brmh_d # 2), lifeState (brmh_d # 2),
 (brmh_d # 2) getVariable ["ACE_isUnconscious", false], damage (brmh_d # 2), speed brmh_d_hunter]
""")
attempt(harness, "unload", "[brmh_d # 2] call ace_common_fnc_unloadPerson")
time.sleep(5)
trace(harness, "brmh_d", 6, 3)
attempt(harness, "tent", """
private _hurt = brmh_d # 2;
brmh_d_tent = createVehicle ["Land_MedicalTent_01_MTP_closed_F", getPosATL _hurt, [], 3, "NONE"];
[typeOf brmh_d_tent, round (brmh_d_tent distance2D _hurt), _hurt call ace_medical_treatment_fnc_isInMedicalFacility]
""")
attempt(harness, "full heal", "[brmh_d # 2] call ace_medical_fnc_fullHeal; true")
time.sleep(6)
trace(harness, "brmh_d", 3, 3)
attempt(harness, "follow", "(brmh_d # 2) doFollow (brmh_d # 0); [lifeState (brmh_d # 2), damage (brmh_d # 2)]")

section("E: the leader goes down")
run(harness, """
brmh_e_from = [1500, 2800, 0];
brmh_e = [brmh_e_from] call brmh_fnc_squad;
[brmh_e # 0, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
time.sleep(5)
LEADER = """
private _group = group (brmh_e # 1);
[name leader _group, leader _group isEqualTo (brmh_e # 0), lifeState (brmh_e # 0), round ((brmh_e # 1) distance2D brmh_e_from),
 round ((brmh_e # 2) distance2D brmh_e_from), currentCommand (brmh_e # 1)]
"""
attempt(harness, "before", LEADER)
run(harness, """
private _group = group (brmh_e # 1);
private _wp = _group addWaypoint [[1500, 2950, 0], 0];
_group setCurrentWaypoint _wp;
true
""")
for _ in range(5):
    time.sleep(6)
    attempt(harness, "  order, leader down", LEADER)
run(harness, "group (brmh_e # 1) selectLeader (brmh_e # 1); true")
for _ in range(4):
    time.sleep(6)
    attempt(harness, "  new leader", LEADER)
attempt(harness, "wake him", "[brmh_e # 0] call ace_medical_fnc_fullHeal; true")
time.sleep(10)
attempt(harness, "  awake", LEADER)
attempt(harness, "  where", "[round ((brmh_e # 0) distance2D brmh_e_from), group (brmh_e # 0) isEqualTo group (brmh_e # 1)]")

section("G: ACE's AI medic, with no enemy around")
run(harness, """
brmh_g_from = [1500, 3100, 0];
brmh_g = [brmh_g_from, false] call brmh_fnc_squad;
(brmh_g # 1) setPosATL [1530, 3100, 0];
[brmh_g # 2, 0.7, "body", "bullet"] call ace_medical_fnc_addDamageToUnit;
[brmh_g # 2, true, 0, false] call ace_medical_fnc_setUnconscious;
true
""")
for _ in range(20):
    time.sleep(6)
    attempt(harness, "  medic", """
    private _h = brmh_g # 2;
    [round ((brmh_g # 1) distance2D _h), _h getVariable ["ACE_isUnconscious", false], lifeState _h,
     _h getVariable ["ace_medical_woundBleeding", 0], _h getVariable ["ace_medical_bloodVolume", 6],
     _h getVariable ["ace_medical_heartRate", 0], animationState (brmh_g # 1)]
    """)
harness.stop()
print("done", flush=True)
