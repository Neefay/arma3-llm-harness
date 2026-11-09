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

## Questions for the owner

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

## Recommendation: talk-on

A station that can see the enemy, named as `observer` on the CAS order as for fire missions, passes the pilot what it sees: the enemy it knows about within the radius, at its own level of knowledge. That's a radio talk-on, and it moves knowledge from one station to another, so it isn't a leak. In model terms it's an arrow from `Knowledge(observer)` to `Knowledge(pilot)`, which needs a line in the model. It would also cover question 1(b) without a laser.
