# Fire support spikes

Throwaway engine tests behind [docs/COMMANDER_FIRE_SUPPORT.md](../../../../docs/COMMANDER_FIRE_SUPPORT.md). They boot a headless game if none is running, and run from this folder:

    ..\..\..\.venv\Scripts\python.exe spike_arty_1.py

1. Guns, ranges, ammunition and what a mission fires
2. Accuracy, check fire, postures, retargeting, reloads
3. Seats, mounting, leaving, and what breaks a crew
4. Shell effects, blame, buildings, smoke, sight, several guns, a vehicle ride, impossible shots
5. Noticing abandoned guns, ruins, a crew under assault
6. What stops a gun firing on its own

7. Crews under assault, long fights, smoke, dust, lethality, vehicle guns, check fire, rides, costs
8. Scorcher ranges, rocket impacts, flares at night
9. Guns on a headless client, on a mission with a slot, and light at night
10. The daytime control for 9

`spike_stress.py` samples what can be measured of a squad's stress in a real fight.

`prototype_loop.py` runs one complete fire mission, with a script playing the commander, and says which of its checks passed.

They aren't tests of the harness, and pytest doesn't collect them. Some leave guns and soldiers on the map, so use a fresh game for a clean run.
