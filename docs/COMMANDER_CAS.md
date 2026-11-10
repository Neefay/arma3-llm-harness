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

## What the established codebases do (read 2026-11-09)

Antistasi, BromA, ACE3, LambsDanger and CBA were read for how they make an AI aircraft attack. LambsDanger and CBA have nothing for it. The rest, by how much of the attack is left to the engine:

| Mechanism | Where | Flight | Firing | Aim or guidance | Takes a bare grid |
|---|---|---|---|---|---|
| SAD over the area, with enemies revealed by a spotting check | Antistasi UAV support | engine | engine | engine | only if something is there |
| Flight through the grid on waypoints, weapons released on a timer | Antistasi airstrike | engine | script | none (Antistasi spawns the bombs; real pylon bombs would work) | yes |
| A real missile steered to a position | Antistasi SEAD | engine | script | engine, with `setMissileTargetPos`, on a patched ammo class (`manualControl = 1`) | yes |
| ACE guided bombs on a virtual laser or a GPS aim point | ACE3 `missileguidance`, `laser` | not covered | not covered | ACE steers the real bomb; no designator unit needed | yes |
| Plane flown on rails at the point, firing every weapon | BromA `fn_cas.sqf` (a copy of Arma's CAS module), Antistasi CAS and dive runs | script | script | the nose points at it; Antistasi also re-aims each round | yes |

What this corrects in the spikes above:

- **Guided weapons can be steered to a grid.** The spike's GBU-12s and Mavericks ignored `setMissileTarget` and `setMissileTargetPos` most likely because vanilla ammo has no `manualControl`. Antistasi patches its HARM with exactly that, then steers it to a position. A config patch needs an addon, not a mission, and the harness has one (`@brmh`). This still needs a spike to confirm for a GBU-12.
- **ACE can guide a released bomb onto a point** with its own GBU-12 or SDB loaded on the pylons. Either a virtual laser emitter registered by script (no unit designating), or the GPS aim point. That only works where ACE is loaded: the Stratis profile has a `commander_stratis_ace` variant.
- **A laser spot can be kept alive.** BromA resets its position every few seconds, because the engine deletes one nobody designates.

### Options

1. **Engine CAS with a spotting check.** A SAD waypoint over the grid, as now. Each cycle the pilot gets a fair chance to spot enemies near the grid: line of sight from the aircraft, then a chance by distance and cover, as Antistasi models it. Those he spots are revealed to him. Flight, firing and aim stay the engine's own; only the pilot's search is modelled. It would fix the prone-infantry problem honestly, by giving the pilot a search instead of telling him where they are. An empty grid still gets no attack.
2. **A strike on coordinates.** The aircraft flies through the grid on ordinary waypoints, and the script releases real pylon weapons at a computed point. Choose one:
   - a) ACE guided bombs, steered by a virtual laser or a GPS point at the grid;
   - b) a patched ammo class with `manualControl`, steered by `setMissileTargetPos`;
   - c) unguided bombs, landing where the release puts them.

   Only the release timing is scripted, plus the guidance target in a) and b). That's roughly what a pilot does with a grid-only fire mission.
3. **Avoid:** flying the plane on rails, or spawning bombs under it. Either replaces the aircraft's own flight or weapons with script.

My recommendation is 1 for close support, where the pilot attacks what he finds, and 2a or 2b for "bomb this grid". They'd be two order types, or two modes of `CAS`.

**Option 1 is built** (the owner chose it, 2026-11-09). While the aircraft is over the grid or engaging, the sortie machine's `EVERY` step runs `brmh_cmd_fnc_sortieSearch`. Each enemy within the order's radius of the grid, with no terrain or object between it and the aircraft, is seen with a chance per second of `0.05 × camouflage × stance × e^(−distance from the grid / 500) × e^(−distance from the aircraft / 3000)`. That's Antistasi's model; the stance factor (prone 0.3, crouching 0.6) is ours. Whoever is seen is revealed to the crew. Live, against the same squad lying in grass that three sorties had missed, the Blackfoot reported contact 15 s after reaching the grid and its gunner killed all six in under five minutes.

## The owner's decisions (2026-11-09)

- **Close support:** option 1, the pilot's search. Built.
- **Strikes on a bare grid:** option 2a, ACE guided bombs. ACE stays optional, so without ACE the same order falls back to unguided bombs released at the computed point.
- **Starting state:** airborne, on station.
- **Contact reports from the air:** bearing and range from the grid the pilot was given, never a grid of his own.
- **Time on station:** a scenario setting. When it runs out the pilot says so ("bingo") and leaves; there's no limit if it isn't set.

## Questions for the owner (as first asked; answered above)

1. **A bare-grid strike.** It isn't possible with unscripted AI. The options above replace my earlier (a) to (c). The options are:
   - (a) `SAD` only. The pilot needs to see something.
   - (b) A real laser from a real unit: a JTAC station with a designator lases the grid. This needs another spike, to check that AI pilots attack a laser held by a unit.
   - (c) A computed release point for unguided bombs. The release is scripted; the bomb and its errors are real.

   My recommendation is (a) now and (b) next. (c) crosses the line that fire support drew.
2. **Starting state.** Airborne and on station from the start, as drafted, or taking off from an airfield, which is slow and unreliable for AI? I recommend airborne.
3. **Contact reports from the air.** Relative to the grid the pilot was given ("60 m east of your grid"), or bearing and range from the aircraft, which means nothing to someone on the ground?
4. **Time over target and fuel.** Is a fixed time over the target enough? Should there be a total time on station before the aircraft leaves?
5. **Weapon choice.** Should the commander choose weapons, or the pilot? AI pilots pick on their own. Restricting them means removing the other magazines for the run.
6. **Helicopters.** The Blackfoot did better than the A-164 against infantry. Should a scenario offer both?

## First cut (built and played live)

The `CAS` order is realised as a `SAD` waypoint on the declared state-machine runner. The aircraft spawns flying (a scenario vehicle with `fly: <metres>`), crewed by its station (`crew: { V1: [driver, gunner] }`), and circles where it starts until it's needed. The machine is `brmh_cmd_sortieMachine`, charted in the model's appendix.

What the pilot says, as played on Stratis (`scenarios/commander/stratis_cas.yaml`, live scene "stratis: close air support"):

```text
Hawg: Copy, grid 037 024, on the way. Under a minute out.
Hawg: Over grid 037 024, looking.
Hawg: Contact, a few contacts, bearing 330, roughly 200 metres; one contact, bearing 340, roughly 200 metres. Engaging.
Hawg: Engaging, guns.
```

The gunner killed four of the six in about 1.5 s from about 350 m, and Recon killed the other two when they walked into it.

Two findings:

- **Prone infantry in grass are invisible from the air.** With the squad set to hold, its men saw the helicopter and lay down. The crew passed within 74 m three times and never detected them (`knowsAbout` 0), so each sortie ended "Nothing seen around grid 037 024, returning to hold." Revealed by script, the same crew fired within a minute. This is fog, not a fault, but it makes CAS useless against an enemy that has gone to ground, unless someone on the ground can show the pilot where they are.
- **The pilot's contact report uses the existing words:** bearing and range from the aircraft. That's question 3.

## Strikes on a bare grid (built, 2026-11-09)

The `STRIKE` order (`at`: a grid only, `bombs`: 1 to 4, `heading`: optional run-in direction) drops bombs on a grid whether or not anything is seen there. The game side is `brmh_cmd_strikeMachine`, charted in the model's appendix.

- **Flight is the engine's.** The aircraft flies to a run-in point 9 km out on the heading, or straight in if it's already over 8 km away and no heading was given. Then it flies ordinary waypoints through the grid, to a point 6 km beyond it. It flies `CARELESS` and holding fire, so it doesn't break off to fight on the way. Planes climb to at least 700 m for the run.
- **How AI pilots fly the run** (`spike_strike.py`, A-164 on Stratis), and why it's set up this way:
  - From a run-in point 5 km out, the pilot comes out of his turn 10-13° off the grid and is still 5° off at 1 km. From 9 km he's on line by 8 km.
  - With the grid as his last waypoint, he starts to turn to circle it, so a waypoint beyond keeps him straight.
  - From the south-west of grid 037 024 he bends around the hills, the same way every time, enemy or not. He's 450 m off line 2 km out and back over the grid at the end. From the south, over the sea, he stays within 1-5°.
  - The heading is the commander's to choose, for the ground as well as for his own men. Guided bombs don't mind; unguided ones on a bent run aren't released ("Couldn't line up").
- **Only the release is scripted.** It's checked every frame while the aircraft is on the run, and a stick goes a third of a second apart.
- **With ACE**, the aircraft's bombs are swapped at spawn for ACE's guided versions of the same bombs (`ace_missile_gbu_*`, `ace_missile_sdb_*`), wherever ACE has one. A laser bomb gets a laser shone straight down on the grid by nobody, which is ACE's virtual emitter (`ace_laser_fnc_laserOn`, code 1111). It's left on for a minute after the release. A GPS bomb gets ACE's aim point set to the grid as it's released. Guided bombs go inside 2.4 km, with the aircraft tracking within 15° of the grid (its velocity, not its nose, which sits 10-15° off).
- **Without ACE**, the pilot uses dumb bombs: no `laserLock` or `irLock`, such as the Mk82. A dumb bomb is released when the impact it would make lands on the grid, within 80 m to the side of it, and the rest of the stick follows a third of a second apart. The impact is predicted from the aircraft's position and velocity, flying the bomb as the engine does. A bomb is a missile with an axis, which starts along the release velocity and turns toward its own (6.9 per second). Drag acts along the axis (k = 0.000225, as k|v|), and the ammo's side friction (`maneuvrability`, 4.6 for the Mk82) damps velocity across it, which holds the fall back like lift. Fitted to three recorded Mk82 drops, it predicts the 1.8-1.9 km throws within 25 m. Gravity and drag alone came out 300 m short. The engine's own laser bombs can't be used for a grid: with nothing locked they glide on for kilometres. An aircraft carrying only those says "Unable, my bombs need a laser on the target."

Measured first (spikes `spike_ace_bombs.py`, `spike_bomb_drag.py`, on Stratis with ACE loaded):

| Bomb | Aircraft | Release | Landed from the grid |
|---|---|---|---|
| ACE GBU-12, virtual laser | A-164 | 2.5 km and 2.4 km out, 860 m up, 512-563 km/h | 0 m, 0 m |
| ACE SDB, GPS | Black Wasp | 2.3 km out, 840 m up, 820 km/h | 1 m |
| vanilla GBU-12, nothing locked | A-164 | 2.5 km out, 800 m up | glided 6.5 km, into the sea |
| Mk82, released at nothing | A-164 | 3.1 km out, 800 m up | 1.2 km short: ballistic, 15.5 s, throw 1.9 km |

What the pilot says: "Copy, two bombs on grid 037 024." Then "In hot, grid 037 024.", "Two bombs away." and "Off target, returning to hold." Or "Not lined up, going around." once, then "Couldn't line up on grid 037 024, returning to hold." As with fire missions, nobody says what the bombs hit unless someone sees it.

## Recommendation: talk-on

A station that can see the enemy, named as `observer` on the CAS order as for fire missions, passes the pilot what it sees: the enemy it knows about within the radius, at its own level of knowledge. That's a radio talk-on, and it moves knowledge from one station to another, so it isn't a leak. In model terms it's an arrow from `Knowledge(observer)` to `Knowledge(pilot)`, which needs a line in the model. It would also cover question 1(b) without a laser.
