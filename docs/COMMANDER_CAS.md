# Close air support: findings and design draft

Status: draft for the owner's review, 2026-11-08. Nothing here is merged. The spikes are in `host/tests/spikes/cas/`.

## What the engine does (measured on Stratis)

All runs used a real aircraft, loitering 2 km from an open grid, then given a task.

| Test | Aircraft | Result |
|---|---|---|
| Laser spot (`LaserTargetE`, then `W`), `DESTROY` waypoint on it, revealed | A-164 | Circles 300 to 800 m from the spot for 4 minutes. Never fires. |
| Same, plus datalink (`reportRemoteTarget`, `confirmSensorTarget`), `doTarget`, `doFire` | A-164 | Same. Never fires. |
| `SAD` waypoint on 4 infantry and an armed Ifrit | A-164 | Detects 1 of 7 after about 45 s. One 30 mm gun run, 131 rounds, landing 40 to 100 m from the grid. Kills nobody. Then cruises. |
| `SAD` waypoint, same enemies | AH-99 Blackfoot | Detects one within 45 s, one 20 mm burst, kills him. Then hovers with nothing else known. |
| Real run over the grid; script releases a GBU-12 by `fireAtTarget` on a laser spot | A-164 | Bombs fall unguided: 580 m and 206 m off. |
| Same with `setMissileTarget` (laser spot), or `setMissileTargetPos` (the grid) | A-164, GBU-12 and Maverick | No guidance either way. The laser spot is deleted within a minute when nothing designates it. |

So:

1. **AI pilots attack what they detect themselves, and only that.** A `SAD` waypoint on a grid is a real, unscripted attack. It is weak against infantry in cover, which is the fog the owner wants: the pilot only engages what he sees.
2. **No AI aircraft will bomb a bare grid.** Nothing I tried got guided munitions onto an unmarked point. A scripted release drops dumb bombs, and those need a computed release point to land anywhere near.

## Design draft

It follows the fire-support rules (see the `commander-radio-realism` note): a real aircraft does the work, directed by grid, and the commander gets no more than a pilot would say.

### The station

An aircraft is a station like a gun crew: `Hawg`, role "close air support, one A-164". The scenario places it airborne, loitering over a holding grid (`hold: "020 015"`). Its crew are its members.

### The order

```text
CAS  at: <grid, 6 or 8 figures>  radius: <m, default 150>  [weapons: GUN | ROCKETS | ANY]
```

- **Lane:** Guns, one per aircraft. **Ending:** Finite. **Claims:** Crew. **Realisation:** Engine (a `SAD` waypoint).
- Grid only, as for fire missions. Markers and building ids are refused.
- **Finished when** the pilot has nothing left to engage at the grid, or after a time limit (the scenario's, say 5 minutes over the target). The aircraft then returns to its hold.
- `CHECK_FIRE` to an aircraft aborts the run.

### What the pilot says

| When | Words |
|---|---|
| Accepted | "Hawg, copy, grid 037 024, about 2 minutes out." |
| Over the grid | "Hawg, over the grid, looking." |
| Engaging | "Hawg, engaging, a vehicle 60 m east of your grid." |
| Weapons | "Hawg, guns." / "Rockets away." / "Bombs away." |
| Nothing seen | "Hawg, nothing seen around your grid, returning to hold." |
| Done | "Hawg, off target, returning to hold." |
| Out of ammunition | "Hawg, Winchester." |
| Hit | "Hawg, taking fire." Lost aircraft: silence, as for any lost station. |

The pilot's contact report names a place relative to the grid he was given, which is how pilots talk. Open question 3 asks whether that's acceptable under the no-grids-in-contact-reports rule.

### Splash and damage

Nobody but an observer reports what the strike hit, as with fire missions. Observers (`spotter: true`) report impacts on the enemy they see.

## Questions for the owner

1. **A bare-grid strike.** It isn't possible with unscripted AI. The options are:
   - (a) `SAD` only. The pilot needs to see something.
   - (b) A real laser from a real unit: a JTAC station with a designator lases the grid. This needs another spike, to check that AI pilots attack a laser held by a unit.
   - (c) A computed release point for unguided bombs. The release is scripted; the bomb and its errors are real.

   My recommendation is (a) now and (b) next. (c) crosses the line that fire support drew.
2. **Starting state.** Airborne and on station from the start, as drafted, or taking off from an airfield, which is slow and unreliable for AI? I recommend airborne.
3. **Contact reports from the air.** Relative to the grid the pilot was given ("60 m east of your grid"), or bearing and range from the aircraft, which means nothing to someone on the ground?
4. **Time over target and fuel.** Is a fixed time over the target enough? Should there be a total time on station before the aircraft leaves?
5. **Weapon choice.** Should the commander choose weapons, or the pilot? AI pilots pick on their own. Restricting them means removing the other magazines for the run.
6. **Helicopters.** The Blackfoot did better than the A-164 against infantry. Should a scenario offer both?

## First cut

What can be built now without those answers: the `CAS` order realised as a `SAD` waypoint, on the declared state-machine runner (holding, inbound, over the target, returning). It would get the radio lines above, a Stratis scenario with a Blackfoot, and a live battle.
