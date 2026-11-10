"""An aid post's tent, the way AID_POST makes one: does a truck still flatten it, and can a shell still destroy it?"""
import time

from spike_ace_lib import game, run, show

from arma_harness.commander.operator import load_sqf

harness = game()
run(harness, load_sqf("commander_boot.sqf"))
run(harness, """
brmh_fnc_tent = {
    params ["_at"];
    private _tent = createVehicle ["Land_MedicalTent_01_MTP_closed_F", _at, [], 0, "CAN_COLLIDE"];
    _tent allowDamage false;
    _tent
};
brmh_plain = createVehicle ["Land_MedicalTent_01_MTP_closed_F", [1500, 2000, 0], [], 0, "CAN_COLLIDE"];
brmh_kept = [[1500, 1000, 0]] call brmh_fnc_tent;
brmh_fnc_truck = {
    params ["_from", "_to"];
    private _truck = createVehicle ["B_Truck_01_transport_F", _from, [], 0, "CAN_COLLIDE"];
    _truck setDir (_from getDir _to);
    private _driver = (createGroup [west, true]) createUnit ["B_Soldier_F", _from, [], 0, "CAN_COLLIDE"];
    _driver moveInDriver _truck;
    _driver setBehaviour "CARELESS";
    _driver disableAI "AUTOCOMBAT";
    [_truck, _driver]
};
true
""")
READ = """
[alive brmh_plain, round (damage brmh_plain * 100) / 100, alive brmh_kept, round (damage brmh_kept * 100) / 100,
 round (brmh_t1 distance2D brmh_plain), round speed brmh_t1, round (brmh_t2 distance2D brmh_kept), round speed brmh_t2]
"""
# Driven straight through at speed, by script, so that it can't steer round them.
run(harness, """
brmh_t1 = ([[1500, 1960, 0], [1500, 2040, 0]] call brmh_fnc_truck) # 0;
brmh_t2 = ([[1500, 960, 0], [1500, 1040, 0]] call brmh_fnc_truck) # 0;
true
""")
time.sleep(2)
run(harness, """
[] spawn {
    private _until = time + 9;
    while {time < _until} do {
        {
            _x setDir 0;
            _x setVelocity [0, 12, 0];
        } forEach [brmh_t1, brmh_t2];
        sleep 0.05;
    };
    {
        _x setVelocity [0, 0, 0];
    } forEach [brmh_t1, brmh_t2];
};
true
""")
for _ in range(4):
    time.sleep(3)
    show("[plain alive, damage, kept alive, damage, t1 to plain, speed, t2 to kept, speed]", run(harness, READ))
print("shells on the kept one, by the same call a real gun's shell makes", flush=True)
run(harness, "brmh_cmd_posts = [brmh_kept]; true")
for offset, ammo in ((0, "Smoke_82mm_AMOS_White"), (25, "Sh_82mm_AMOS"), (2, "Sh_82mm_AMOS"), (2, "Sh_82mm_AMOS"), (2, "Sh_82mm_AMOS")):
    run(harness, f"""
    [(getPosASL brmh_kept) vectorAdd [{offset}, 0, 0], "{ammo}"] call brmh_cmd_fnc_shellOnPosts;
    true
    """)
    show(f"  {ammo} at {offset} m", run(harness, "[alive brmh_kept, round (damage brmh_kept * 100) / 100]"))
    time.sleep(1)
harness.stop()
print("done", flush=True)
