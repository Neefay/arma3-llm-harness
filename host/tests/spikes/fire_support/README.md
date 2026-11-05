# Fire support spikes

Throwaway engine tests behind [docs/COMMANDER_FIRE_SUPPORT.md](../../../../docs/COMMANDER_FIRE_SUPPORT.md). They boot a headless game if none is running, and run from this folder:

    ..\..\..\.venv\Scripts\python.exe spike_arty_1.py

1. Guns, ranges, ammunition and what a mission fires
2. Accuracy, check fire, postures, retargeting, reloads
3. Seats, mounting, leaving, and what breaks a crew
4. Shell effects, blame, buildings, smoke, sight, several guns, a vehicle ride, impossible shots
5. Noticing abandoned guns, ruins, a crew under assault
6. What stops a gun firing on its own

`prototype_loop.py` runs one complete fire mission, with a script playing the commander, and says which of its checks passed.

They aren't tests of the harness, and pytest doesn't collect them. Some leave guns and soldiers on the map, so use a fresh game for a clean run.
