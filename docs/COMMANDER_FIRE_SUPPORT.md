# Commander Mode: fire support design

**Status:** built and passing live, as of 2026-11-05, and not yet tried by an LLM. Where the build differs from the design, [section 14](#14-build-order) says so. Every engine fact below was measured on Arma 3 2.22 in throwaway tests, unless it's listed under [Still unverified](#12-still-unverified). Written 2026-11-05. It extends [COMMANDER.md](COMMANDER.md), and the fog rules there still apply.

## 1. Summary

The commander gets real guns. A squad mounts a mortar on order, the commander calls fire on a place, and a real AI gunner fires real shells that can land anywhere it was told, including on friendlies. Nothing warns it. It only learns where rounds landed if someone is watching, and only a trained spotter can say how far off they were.

This is bigger than a new order type. Vehicles become things the commander knows about and orders people into, so this design also covers vehicles and crews in general.

**The owner's requirements:**

1. Fire always comes from a real gun, and is never spawned through scripts.
2. The commander knows where serviceable weapons are, within the fog.
3. Reports say what vehicle a station is in.
4. The commander can order men into a specific seat: "Enter this mortar as gunner".
5. A station has a flag for correcting fire. Anyone can report an enemy to shell, but correcting fall of shot takes a specialist.

**The yardstick:** the goal is a challenge in a game, not a commander that wins. A commander that shells its own men on a stale report is the fog working, and it stays possible. There are no safety rails. A harness fault that caused it would be fixed at once, so the records have to be able to tell the two apart ([section 9](#9-telling-fog-from-a-bug)).

## 2. What the engine does

### 2.1 Guns

| Fact | Measured | Design consequence |
|---|---|---|
| Vanilla guns | Mk6 mortar, M4 Scorcher, 2S9 Sochor, M5 Sandstorm, Zamak MRL, Mk45 ship gun | Find them with `artilleryScanner`, not a class list. First version: mortars, then tube guns, with rockets left out (section 12) |
| Mortar reach | In range at 50 m to 4,000 m, not at 10 m or 6,000 m | Check before firing |
| Scorcher and Sandstorm reach | Not in range up to 800 m, in range from 1,200 m | Too far for a small map: start with mortars |
| Mortar load | 4 HE magazines of 8, plus 8 smoke, 8 flare and 8 illumination | Words for the commander: HE, SMOKE, FLARE, ILLUM |
| Rate of fire | First round about 2 s after the order, then one every 1.8 s | |
| Flight time | 14 s at 100 m, 14 s at 300 m, 28 s at 800 m, 40 s at 2,000 m, 36 s at 3,500 m. `getArtilleryETA` agreed | It isn't linear, so never estimate it |
| Accuracy over 8 rounds | Mean miss 5 m at 100 m, 7 m at 300 m, 10 m at 800 m, 14 m at 2,000 m, 16 m at 3,500 m. Worst 32 m | Far better than a 100 m grid square, so the aim point is the main error, which is what makes spotting and 8-figure grids matter |
| Asking for 12 rounds | Fires 8, then stops at the end of the magazine | The controller re-issues in chunks |
| Next magazine | 7.4 s after the last round | |
| Changing shell type | 6 to 7 s | |
| Asking for 0 rounds | Fires a burst of 4 | Reject rounds below 1 |
| New mission during a mission | Replaces it at once, and the new aim was hit | Retargeting needs nothing special |
| One round per aim point (as LAMBS does) | 2.4 s per round, landed 6 to 13 m from each aim | This is how `radius` works |
| Two guns in one group | Each fires and stops independently | A station can hold several guns |
| Damage 0.8 | Still fires | Damage isn't a reliable status |

**Four silent failures.** Each of these does nothing, with no error, and `unitReady` stays true, so the controller checks the first three beforehand, and catches the fourth with a timer:

- Target out of range, too near or too far (`inRangeOfArtillery` is false).
- Gun has no gunner.
- Gunner is dead.
- The gun says it can reach, and doesn't fire. A Scorcher did this at 2,000 m, in 3 of 3 tests.

### 2.2 The gun fires on its own

**A crewed mortar fires at enemies its crew knows of, without any order.** In an assault test with no fire order given, one gun fired 16 rounds at 6 attackers about 225 m away, and all 6 were dead within 60 seconds. Its squad's rifles were firing too, and who killed whom wasn't recorded. In a separate test with invulnerable, inert enemies and no rifles, a gun fired 15 rounds in 40 seconds. It'll spend the commander's ammunition, and could kill friendlies, without the commander ever asking.

| Setting on the gunner | Fired by itself in 40 s | Ordered mission |
|---|---|---|
| Nothing | 15 | Fires |
| **`disableAI "TARGET"`** | **0** | **Fires, 3 of 3, 10 to 21 m miss** |
| `disableAI "TARGET"` and `"AUTOTARGET"` | 0 | Fires |
| `disableAI "AUTOTARGET"` | 16 | Fires |
| `setUnitCombatMode "GREEN"` or `"BLUE"`, or group `GREEN` | 0 | Blocked until mode goes back to `YELLOW` |
| `disableAI "WEAPONAIM"` | 0 | Blocked |
| `CARELESS` | 12 | Fires |
| `doStop` | 12 | Fires |
| `enableEngineArtillery false` | 13 | Fires |

So a gunner mounting a gun gets `disableAI "TARGET"`, and gets it back on leaving. Enemy guns leave it off ([decision 4](#13-decisions)). LAMBS adds its own self-firing and crew dismounting on top of this, so the design assumes LAMBS isn't loaded, and says so at startup if it is.

### 2.3 Check fire and postures

| Done during a mission | Rounds after it | Note |
|---|---|---|
| **`doStop` on gun or gunner** | **0** | Leaves `currentCommand` as `STOP`. The next mission clears it without help |
| New one-round mission | 1 | |
| `doMove` | 0 | Also moves him |
| `doWatch objNull` | 0 | One test, and it's not an obvious cause, so not relied on |
| `loadMagazine` | 0 | Changes the shell type |
| `GetOut` action | 1 | He was still on the gun 25 s later |
| `BLUE`, `CARELESS`, `disableAI` of any kind | All of them | **Don't stop a mission once it's running** |

Check fire is `doStop`. Rounds already in the air still land, and at 800 m that's 28 s of them, so the report says so.

A mission started under `GREEN` or `BLUE` doesn't fire. The gunner holds with `unitReady` false and `currentCommand` of `FIRE AT POSITION`, and fires when the mode goes back to `YELLOW`. This is a trap for commanders, because Haiku set its squads to `GREEN` at the start of its battle, so the battery has to say it's holding.

### 2.4 Crews

| Fact | Measured | Design consequence |
|---|---|---|
| Seats | `fullCrew [_v, "", true]` lists every seat with role, cargo index and turret path. Mortar: gunner only. Hunter HMG: driver, gunner, 2 cargo. Scorcher: driver, gunner, commander. Offroad: driver, cargo, and 4 firing seats | Seats come from the game |
| Mounting | `assignAsGunner` plus `[_man] orderGetIn true`. 16 s from 50 m, 47 s from 200 m, leader or not | One man goes, and the others stay |
| Role report | A mortar gunner's `assignedVehicleRole` says `["turret", [0]]`, not `gunner` | Read roles from `fullCrew` |
| Subordinate on a gun, squad ordered to move | He stays on the gun, and the squad leaves without him, 85 m off after 35 s | The squad splits, so say so in the report |
| **Leader on a gun, squad ordered to move** | **He stays on the gun, and stays leader** | **Never put the leader on a gun if anyone else can do it** |
| Getting out | `GetOut` action, `unassignVehicle` and `orderGetIn false`: out within 8 s, then he follows | |
| Seat already taken | Waits nearby with no error (stopped 7.7 m away) | Detect it, and report it |
| Gunner killed | `gunner` is null, the seat counts as empty, the body stays listed in `fullCrew`. Squadmates don't take over | A new man needs a new order, and that worked in under 25 s |
| Gun destroyed | `canFire` false, gunner dead | |
| Out of ammunition | Crew stays on the gun. `someAmmo` false, `getArtilleryAmmo` empty | |
| Empty gun | `canFire` false, though nothing's wrong with it | Don't use `canFire` to judge an empty gun: use `alive`, `damage` and `someAmmo` |
| Enemies 25 m away (inert) | Crew stayed on the gun, squad fought | |
| Vehicle by seats | 4 men into a Hunter, set seats, 22 s from 30 m. A subordinate driver drove the squad 391 m in 25 s on an ordinary waypoint. All 4 out within 12 s | Works for vehicles in general |

### 2.5 What shells do

| Fact | Measured | Design consequence |
|---|---|---|
| `Explode` on each `Fired` shell | Fired for every round, with an exact position (ASL) | This is the source of all reports and the review |
| `Explosion` handler on soldiers | Fired only within about 50 m | Too short for "I can hear that" |
| `Suppressed` handler | Fired at 100 to 200 m for enemy soldiers, **never for friendly ones** | Useless for friendly fire |
| AI reaction | Stayed where they were | Soldiers in the open are easy targets |
| 8 HE on one point, men standing in the open | At 8 m and 25 m: all 8 dead across two tests. At 50 m: 2 dead in one test, 2 alive in the other. At 100 m and beyond: unhurt | Very lethal, so ammunition is the balance lever |
| Who gets blamed | `Killed` gives the gun as killer, its gunner's name, and usually the gunner as instigator, but sometimes null | The review reads the gun, not the instigator |
| Gunner after killing 6 friendlies | Rating 0, still `WEST` | He doesn't turn renegade (one test) |
| Gunner after killing 4 enemies | Rating 800 | |
| What targets learn | `knowsAbout` the gunner was 0 at 800 m | No counter-battery by itself |
| 16 HE on a small house | Destroyed. 3 of 3 inside dead, 2 at 25 m hurt but alive | Shelling works on garrisons |
| 16 HE on a large house | Became a damaged model, still 9 positions. 2 of 3 inside dead | |
| Fully destroyed building | Becomes a `*_ruins_F` object, with no positions. `nearestObject [pos, "House"]` no longer finds it | **`CLEAR` needs a fix** (below) |
| 3 smoke rounds | `checkVisibility` in `VIEW` fell below 0.4 from about 40 s to 100 s after firing, and about 0.02 at worst. In `FIRE` it stayed at 1 | Smoke blinds spotters. Whether it stops AI shooting is unverified |

**`CLEAR` needs a fix, regardless of artillery.** It looks a building up again with `nearestObject [pos, "House"]` each time. Once a building is gone, that can find nothing, or a neighbour, so the squad could report it "checked" without entering. It should hold on to the object from `listBuildings`, and report "B3 is a ruin" when it gets there.

### 2.6 Noticing things

`nearEntities` finds vehicles whether they can be seen or not, `targets` doesn't list empty ones, and `knowsAbout` read 0 for a gun in plain sight at 400 m. `checkVisibility` in `VIEW` from a soldier's eyes gave the right answer: 1 in the open at 80, 400 and 600 m, and 0 behind a house. An empty gun's side reads as civilian. For spotters, the same check from eyes to just above an impact gave 0.8 to 1 in the open and 0 behind a house.

### 2.7 What LAMBS taught

From [LambsDanger](https://github.com/nk3nny/LambsDanger), in `fnc_doArtillery`, `taskArtilleryRegister`, `sideHasArtillery`, `fnc_brainVehicle` and `doGroupStaticDeploy`:

- **Adopted:** checking `inRangeOfArtillery` and `canFire` first, one order per aim point to build a beaten zone, `unitReady` to tell when it's done, `doWatch` to turn the gun first, and `artilleryScanner` plus the weapon's `nameSound` to tell rockets from shells.
- **Interesting for later:** weapon bags (`Weapon_Bag_Base`, `assembleInfo`, `WeaponAssembled`), so a squad could carry and set up a mortar.
- **Not adopted:** LAMBS is a good AI that spots and adjusts by itself. Here, the commander does the thinking, so it isn't a dependency.
- **Different on purpose:** LAMBS refuses or switches to smoke when friendlies are within 150 m. This design doesn't.

## 3. What the commander knows about vehicles

The brief says the commander must know where serviceable weapons are, and that's in tension with the fog, because "serviceable" is something only someone nearby can see. The rule that resolves it:

**The commander knows what it's been told, as of when it was told.** It's the same rule as for buildings and reports.

- **Vehicle list.** Vehicles get ids such as `V1`, listed with buildings in `commander_mission`, the briefing and `commander_map`. Ids are internal labels, with game handles held only on the server.
- **At the start:** the scenario lists the vehicles and guns the force knows about, with where they were last known. Nobody says they still work.
- **Learned later:** any station that can see an unlisted vehicle reports it once, and it gets an id: `Bravo: Mk6 mortar, nobody on it, grid 041 039. Listed as V3.`
- **Status comes only from reports,** each with its age: `V1  Mk6 mortar  grid 041 033  crewed by Hammer  24 HE  3 min ago`.
- **Stale is allowed.** A gun destroyed while nobody's near stays listed. Whoever's sent there finds out.
- **Enemy-crewed vehicles** are contacts as they are today. An enemy gun abandoned or captured can get an id once seen empty.

What counts as a sighting: within 800 m to start with, `checkVisibility` in `VIEW` above 0.3, seen by any living soldier in the station. A station reports what it can plainly see: type and whether anybody's on it, and whether it's visibly wrecked (`alive` false). Up close, within about 50 m, it can also tell whether it has ammunition. It never reads engine damage numbers.

Buildings get the same treatment: a station that can see a destroyed building reports it once, `B3 is destroyed`. Until then the commander's map still shows it standing.

## 4. Orders

```python
# Into a seat: one soldier for gunner, driver or commander. `seats` is how many for cargo.
commander_order(to="Hammer", legs=[{"type": "MOUNT", "vehicle": "V1", "seat": "gunner"}])
commander_order(to="Alpha",  legs=[{"type": "MOUNT", "vehicle": "V2"}])     # everyone who fits, driver and gunner first
commander_order(to="Hammer", legs=[{"type": "DISMOUNT", "vehicle": "V1"}])  # or leave vehicle out, for everyone

# Fire, by grid reference only
commander_order(to="Hammer", legs=[{"type": "FIRE_MISSION", "at": "041 041", "ammo": "HE", "rounds": 2, "radius": 0,
                                    "observer": "Recon"}])
# Correction: a new, more exact grid, which the commander works out from what the spotter said
commander_order(to="Hammer", legs=[{"type": "FIRE_MISSION", "at": "0408 0416", "ammo": "HE", "rounds": 6, "radius": 30}])
commander_order(to="Hammer", legs=[{"type": "CHECK_FIRE"}])
```

**Fire missions are relayed only as grid references.** An infantry order can say `CLEAR B1`, because "B1" stands in for "that house", which a squad leader can see. A radio operator can't call fire on a token. So `FIRE_MISSION` refuses building and marker ids, and there's no "from last" shortcut: the commander has to work out the grid, and that's where its mistakes can come from.

- **`at`:** 6 figures, the centre of a 100 m square, or 8 figures, the centre of a 10 m square. A 6-figure aim can be up to about 70 m from the real target, and an 8-figure one up to about 7 m, so 8 figures is what makes precise correction possible. 8 figures apply to fire missions and markers, and other orders stay at 6.
- **Where 8 figures come from:** the commander's own arithmetic and map reading. The building list stays at 6 figures, so getting a building's 8-figure grid means reading it off `commander_map`, which can be zoomed to a 50 m radius. A spotter's offset has to be added to the last grid by hand. Mistakes here land on the map as real shells.
- **`vehicle`** must be on the list. Anything else is refused, which reveals nothing.
- **`seat`:** `driver`, `gunner`, `commander`, `cargo`, or `turret:0` and so on, taken from the game's own list. A seat the type doesn't have is refused from the commander's own knowledge of the type.
- **`ammo`:** HE or SMOKE, by mapping the gun's own magazines. Flares do nothing for AI (section 12), so they wait.
- **`rounds`:** 1 up to a limit, default 3, per gun. Chunks across magazines are the controller's problem.
- **`radius`:** 0 to 150 m. Above 0, each round gets its own aim point in the radius, so the rate of fire drops slightly.
- **`observer`:** a station to watch this mission ([section 6](#6-watching-the-fall-of-shot)).
- **`guns`:** optional list, default all guns the station has crewed.
- **Timed:** `commander_schedule` already takes an order, so smoke at T+12:00 and fire together work with no new mechanism.
- **Who can:** `MOUNT` and `DISMOUNT` need that capability. `FIRE_MISSION` and `CHECK_FIRE` need theirs, plus a gunner at the time, which is checked in the game rather than at order time.

**Who gets picked for a seat.** The newest member first, never the leader unless he's the only one left. Asking for a seat when only the leader is left takes him, and that squad reports it can't move as a group until he's down.

**A squad with a man on a gun, ordered to move:** he stays, and the acknowledgement says so: `Copy, moving to grid 041 040. Reed stays on V1.` It's what the engine does, it's a reasonable way to leave a gun crewed, and it needs saying.

**A leader on a gun, ordered to move:** he doesn't go, so the order must get him off first. Dismount him, then move. Otherwise the squad sits still while reporting it's moving.

## 5. Reports

All worked out from what the station can really observe, then worded the same way as today.

**Mounting:**
```text
Copy, Reed mounting V1 as gunner.
Reed on V1 as gunner.
Unable, V1's gunner seat is taken.
V1 is wrecked. Not mounting.
Unable, can't reach V1.                 (nobody on it after a time limit based on distance)
Gunner down on V1.                      (his own squad knows at once)
```

**Firing:**
```text
Copy, fire mission, 6 HE at grid 041 041.
Shot, 6 rounds, splash in about 30 seconds.
Rounds complete. 26 HE left.
Delay on the gun, mission still on.    (currentCommand is FIRE AT POSITION, nothing fired after 8 s)
Unable, out of range.
Unable, can't lay on that target.           (unitReady, all checks passed, and nothing fired after 10 s)
Unable, no gunner on V1.                    (when the order names V1)
Unable, no gun crewed.                      (when it doesn't, and the squad isn't on one)
Out of HE, 2 of 6 fired.
Copy, check fire.
3 rounds still in the air.
V1 destroyed, 2 of 6 fired.                 (if crew or squad survive to say so; otherwise silence, as usual)
```

**SITREP topics:** a new `vehicles` topic, and `ammo` includes a crewed gun's rounds by type: `Reed on V1 as gunner, 3 on foot. V1: 24 HE, 8 smoke.`

**Under fire.** The AI's own events can't be used, as section 2.5 shows, so these come from the real shells. Every `Explode` is checked against every station:

| Distance from the nearest soldier | Report |
|---|---|
| Within 100 m | `Under indirect fire, explosions about 50 m north.` PRIORITY, once per burst |
| 100 to 400 m | `Explosions to the north, roughly 200 m.` ROUTINE, once per burst, and only if not already reported in the last minute |
| Beyond 400 m | Nothing |

No station ever says whose shells they were, because it can't know. Casualties use the existing report. **This applies to every shell, friendly or enemy.**

## 6. Watching the fall of shot

A new station field, `spotter: true`. Reports depend on who's watching:

| Who | Can it see the impact? | Report |
|---|---|---|
| Assigned `observer`, and a spotter | Yes | `Splash 60 m north, 20 m east of the enemy. 3 rounds seen.` |
| Spotter, not assigned | Yes | `Splash seen, grid 041 041, about 300 m north of us.` |
| Spotter, assigned | No | `Can't observe. No view of the target.` once, with the reason if it's smoke being unknowable |
| Not a spotter | Either | Only the "under fire" and "explosions" reports above |

- **An ordinary soldier still reports enemies,** through contact reports, as today. That's how they call for shelling, in effect. They just can't correct it.
- **Can it see?** At the moment of each impact, checked from any living soldier in the station: `checkVisibility` in `VIEW`, from eyes to 1 m above the impact, above 0.3, within 1,500 m. Smoke and the dust of earlier rounds block it for free, so in a salvo only the first round is seen, and adjusting calls for single rounds at least 10 s apart. The doctrine has to say so.
- **Grouped:** one report per burst, a few seconds after the last round lands. Offsets are rounded to 10 m up to 100 m, then to 50 m. That keeps it good enough to correct, and not perfect.
- **Against what:** the enemy the spotter can see, at the position it perceives them, because that's what an observer corrects onto. An offset from the aim point would tell the commander nothing if the aim was wrong to begin with. With no enemy in view, it's against the grid it was given, which is what assigning an observer tells it.
- **The correction is the commander's job.** The spotter says where it landed, and the commander works out the new grid. A report may not name friendlies near the impact, unless they're that spotter's own station.

This gives the classic loop: a first round off by up to the grid's error, the observer calls it, the commander works out a corrected 8-figure grid and sends it, then fire for effect. Without a spotter, it can still fire by map, at unknown effect, and find out only from casualty reports or an enemy that stops showing up.

## 7. How it runs in the game

Server-side, in `adapters/commander/fire/` (`machine_fire.sqf`, `fn_stepFire.sqf`), on a CBA per-frame handler every 0.5 s while any mission is active, and the 2 s step otherwise. Each gun has a small state machine:

```text
IDLE -> (FIRE_MISSION) -> checks -> AIMING -> FIRING -> DONE -> IDLE
                           |                     |  ^
                           v                     v  |
                        UNABLE              RELOAD/NEXT CHUNK
                                                 |
                       HOLDING <- nothing fired after 8 s, currentCommand FIRE AT POSITION
```

1. **Checks, in order:** gun `alive`, gunner `alive`, shell type left, `inRangeOfArtillery`. A failure becomes a radio report.
2. **Aim:** `doWatch`, then `doArtilleryFire`. Never a mission of more than what's left in the magazine, and one round at a time if `radius` is above 0.
3. **Fired handler:** counts rounds, records each with mission id, and adds the projectile's `Explode` handler. The handler is on the gun from when it's enrolled, so self-fired rounds and enemy guns are recorded too.
4. **Next chunk:** when `unitReady` and rounds remain, send the next. If a chunk stops short because of a gunner's death or similar, the checks catch it.
5. **Check fire:** `doStop` on the gun, clear the remaining rounds, count rounds in the air.
6. **Mount and dismount:** `disableAI "TARGET"` when he gets on, and `enableAI "TARGET"` when he gets off or the gun's lost.

Guns stay real everywhere: **no script may create a shell, and `BIS_fnc_fireSupportVirtual` isn't used.** A test scans the SQF for it.

**The packet** gains `mounted` (each soldier on a vehicle, by id, seat and name), `guns` (ammunition by type, state, rounds fired and in the air), `seen_vehicles` and `seen_ruins`. Trackers turn those into reports, as they do today, so reports stay testable offline. Impacts come as a new event, for the host to judge who could hear and see them. The host needs positions of all stations, which truth already sends; these reports are built from that but say only what the station could observe.

## 8. Fog check

Every new item, against the rules in COMMANDER.md section 13:

| Risk | Answer |
|---|---|
| Order tool shows a gun's dead | Tool results stay "sent", and failures come by radio, from people who are alive to say so |
| `vehicle` id for a destroyed gun | Accepted. It finds out when someone gets there |
| Dead crew | Silence, then "no answer", as today |
| Wording reveals truth | Reports use only what that station can observe, and never engine damage values |
| Who fired | Nobody says, for the battery's own rounds or the enemy's |
| Friendlies near an impact | Spotter doesn't name others, and nothing warns before firing |
| `commander_map` | Shows reported vehicle positions and destroyed buildings only once reported |
| Impact events | Host-only, like truth, and not on the commander's allow-list |

## 9. Telling fog from a bug

The owner's example: if the commander shells its own men, was that a bug in serializing a report, or a stale belief? The records have to answer that, so each mission logs:

- **`fire_missions.jsonl`:** the order, the aim point, and a copy of what the commander had then: its markers, and each station's last reported position and age.
- **`shells.jsonl`:** every round from every gun: mission (or none if self-fired), gun, shell type, time fired and landed, position.
- **`kills.jsonl`:** adds the gun, read from the `Killed` killer.

For each friendly killed by a friendly gun, the review works out what happened:

| Case | What the records show | Verdict |
|---|---|---|
| The commander's last report for that station was old, and it had moved | Report age and true position at firing | **Fog** |
| Its last report was fresh, and already close to the aim point | Report and aim | **The commander's decision** |
| It really had reported a move, and that report wasn't in the briefing | Packet against what was delivered | **Bug**, fix it |
| Self-fired, with `disableAI` meant to prevent it | Mission is none | **Bug**, fix it |

The review page adds impacts and aim points to its maps, and these verdicts to Deaths.

## 10. Failure table

| Situation | What happens |
|---|---|
| Gunner killed mid-mission | Firing stops. `Gunner down on V1. 3 of 6 fired.` Squad doesn't take over unless ordered |
| Gun destroyed mid-mission | `V1 destroyed.` if anyone's left. Otherwise silence |
| All crew dead | Battery goes silent, then "no answer" |
| Squad moves off, leaving a man on the gun | Reported at the time. He stays, and can still fire |
| Whole squad ordered onto a gun | One gets on, others told to stay close. Report says who |
| Gunner mounted when enemies nearby | He doesn't fire by himself, and can't defend himself, since `TARGET` is off. His squad can |
| Two stations sent to the same seat | The second reports the seat's taken |
| Commander shells a building it's sent a squad to clear | That's a choice, and may kill them |
| `CLEAR` on a ruin | `B3 is a ruin.` No walk-through, and next building |
| Mission restart | Same as today, all guns reset |
| Scorcher or a gun on the move | Unverified, see section 12 |

## 11. Scenario format

```yaml
vehicles:
  - { id: V1, class: B_Mortar_01_F, at: "041 033", ammo: { HE: 16, SMOKE: 4 } }
stations:
  - callsign: Hammer
    role: mortar section
    capabilities: [MOVE, HOLD, MOUNT, DISMOUNT, FIRE_MISSION, CHECK_FIRE, HALT, POSTURE]
    at: "041 033"
    units: 2
    crew: { V1: gunner }       # starts mounted
  - callsign: Recon
    spotter: true
    capabilities: [MOVE, HOLD, SENTRY, PATROL, PATROL_AREA, CORDON, HALT, POSTURE]
enemies:
  - { id: East Mortar, class: O_Mortar_01_F, at: "044 045", mode: gun }   # fires by itself, and it's a real gun too
```

`ammo` sets what a gun starts with, because the default of 32 HE is a lot. A new scenario holds this, and `take_the_village` stays as it is.

## 12. Later test results

Every item that was on this list has now been measured on the real game. Most are one or two runs, so they show what happens, not how often. Scripts are `spike_arty_7.py` to `spike_arty_10.py`, and `spike_stress.py`.

| Question | Measured | Design consequence |
|---|---|---|
| A crew alone, assaulted by 6, `TARGET` off | Two runs. Never fired, never dismounted, and killed by T+60 to T+65 | A gun can't defend itself. It needs a squad or a choice to leave it |
| The same, `TARGET` on | Two runs. Fired 8 and 9 rounds at its attackers, and all 6 were dead by T+55 | Self-firing is a very strong defence, so enemy guns are dangerous up close |
| A squad of 4 with a gun, assaulted by 6, `TARGET` off | One run lost one soldier and killed 4 attackers in 2 minutes. The other was wiped out and killed none | High variance. The gunner died and didn't dismount in both |
| `TARGET` off in a long fight | Two runs, 3 minutes each, enemy in plain view: 0 rounds | Reliable so far |
| Contact knowledge with `TARGET` off | The gunner and leader both still listed all 4 enemies, even with the leader on the gun | Contact reports should survive it. Enemies were revealed by script here, so noticing them unaided is untested |
| Dust against spotting | After a shell lands, sight of the impact falls to 1 to 10% for about 5 s, and is back by 9 to 11 s, from 100, 330 or 800 m alike. It's the same looking 8 m above the impact | **A salvo hides itself.** At one round per 1.8 s, only the first can be seen. Check sight at the moment of impact, and adjust with single rounds at least 10 s apart |
| Smoke against spotters | With inert soldiers, 3 rounds cut `VIEW` below 0.4 from about 40 s to 100 s after firing (section 2.5). With 6 rounds in a live fight, it stayed near zero for over a minute | Smoke blinds spotters, including your own |
| Smoke against AI shooting | One run, before and after the rounds landed at about T+58: firing fell only from 3.4 to about 2.6 shots a second, and hits from 1.7 to about 1.0. `FIRE` visibility stayed at 0.69. `VIEW` had already fallen at T+35, before any mortar smoke, and did so in a test with no mortar too, so the soldiers seem to throw their own, which muddies the comparison | **Smoke doesn't stop AI that already knows where you are.** Whether it hides you from new detection is untested |
| AI seeing at night | No night vision, moon down: 0 detections in 110 s at 60 or 120 m, in any light. By day, the same setup noticed within 3 to 5 s, at up to 200 m | **Flares don't help AI see.** Illumination is for people watching, which in this mode means nobody. Leave `ILLUM` and `FLARE` out of the first version |
| Flare and illumination rounds | Burst at about 245 m, 26 s after firing. Flare: 19 s of light, only a little above a site with none, though nearby flares may have lit that site. Illumination: over 50 s, and hundreds of times brighter | They work, and are visually impressive for anyone watching with `--watch` |
| Lethality, 8 HE on one point | Two runs each, 4 men per ring. **At 15 m and 40 m: all dead, whether standing, prone, moving or behind a bag fence.** At 75 m: all alive, except 2 hurt per standing group, and moving men who walked into it (2 and 3 dead) | Far stronger than any cover tested. Being spread out or moving matters, and being prone only reduces wounds. Ammunition is the balance lever |
| Scorcher and Sochor | Gunner alone is enough. First round 7 s after the order, then one every 6 s. 48 s flight at 2,500 m. Missed by 28 to 92 m | Less accurate, and slower to arrive. 7 ammo types, including mines and guided rounds, which are worth leaving out at first |
| **Scorcher at 2,000 m** | 3 of 3 tests fired nothing, though `inRangeOfArtillery` said yes, with `getArtilleryETA` valid and `unitReady` true. Fine at 1,000, 1,300, 1,600, 2,200, 2,500, 3,000 and 4,000 m | **A fourth silent failure.** Probably a gap between charges. Nothing fired after 10 s, with all checks passing, must report `Unable, can't lay on that target` |
| Sandstorm and Zamak rockets | 4 rockets in 2.4 s, first at about 7 s. `Explode` never fires, because each splits in the air at about 437 m | Impacts can't be tracked this way. Leave rockets out of the first version |
| Firing a gun that's driving | A Scorcher at 41 km/h stopped, fired, and stayed stopped, having gone 112 m of 600 | A fire mission cancels movement, so the battery must report it and a move needs reissuing |
| Check fire | Mortar, before the first round and after 4 or 8: nothing further, and the next mission fired. Sandstorm after 2: the same. Scorcher: couldn't be tested, because it hit the 2,000 m gap | Reliable on mortars and rockets |
| A truck and too many men | A truck took 8 within 40 s and drove 492 m in 40 s. A Hunter took 4 of 8: the other 4 stayed out with no complaint | Report who didn't fit |
| A gun crew on a headless client | One test. An order sent from the server fired nothing. The same order through `remoteExec` to the gun fired, and the server saw every `Fired` and `Explode` | **Gun crews stay on the server.** `setGroupOwner` isn't used on them |
| Cost of sight checks | 30 soldiers, one point: 2.3 ms for `checkVisibility`. `nearEntities` 0.17 ms, `fullCrew` 0.05 ms | Fine per shell. Sighting vehicles should be spread over several steps |
| Stress | `getSuppression` averaged up to 76% on the losing side and 39% on the winning one, and fell to 0 within 5 s of the end. A mortar round 90 m away moved nothing | Used for reports (COMMANDER.md 10.6). Shells need their own trigger: count a nearby impact as being in combat |

**Still open:** a real fight with fire support through the commander's own tools, a spotter finding its own targets, moving enemies, whether smoke hides anyone from new detection, and vehicles driving under fire. These belong to the integration steps below.

## 13. Decisions

Agreed with the owner:

1. **Who can crew a gun:** anyone can `MOUNT` anything with a free seat. The `FIRE_MISSION` capability decides whose orders to fire are accepted, so grabbing an abandoned mortar works only for a station trained for it.
2. **Reported vehicles:** named by exact type, such as "Mk6 mortar", once a squad can see one.
3. **Spotter precision:** offsets rounded to 10 m, as in section 6.
4. **Self-firing:** the commander's guns never fire by themselves, and enemy guns do, since that's real engine behaviour and a real threat that needs no script.
5. **Ammunition:** 16 HE and 4 smoke for the test scenario, set per scenario, with no resupply yet.

6. **Fire missions by grid reference only.** No building or marker ids, and no relative shifts. 6 figures, or 8 for precision. See section 4.

Chosen by me and easy to change: the building list stays at 6 figures, so 8-figure grids have to be read off the map. If that proves too error-prone for a model reading an image, the list could give 8 figures instead, which keeps the rule that the commander has to relay a grid.

## 14. Build order

All of these are done, and each passed its live check on the real game, in [live_commander.py](../host/tests/live_commander.py). A scripted fight in `village_with_mortar` then fired all 16 HE at the village through the commander's tools. It killed 2 of the garrison, and the spotter's offsets matched the true positions. What's left is a real LLM run.

1. **Prototype, outside the commander:** done. [prototype_loop.py](../host/tests/spikes/fire_support/prototype_loop.py) drives one full loop on a real game, and passed 16 of 16 checks: mount by seat, no self-firing, impossible shots refused aloud, a 6-figure mission that missed by 45 m on average, a spotter's report, a corrected 8-figure grid that missed by 12 m and killed 4 of 4, a mission across a magazine change, check fire, friendly fire recorded against the gun, and dismounting. A script played the commander, so none of this has been through the commander's tools or reports yet.
2. **Vehicle list and reports:** `V` ids, sightings, the `vehicles` topic, and the `CLEAR` ruin fix.
3. **`MOUNT` and `DISMOUNT`,** and the leader and split-squad rules.
4. **`FIRE_MISSION` and `CHECK_FIRE`,** with the controller.
5. **Impact reports and spotting.**
6. **Records and review:** missions, shells, verdicts, impacts on the maps.
7. **Scenario, doctrine, real LLM run.**

Each step gets offline tests, as the rest of commander mode has, and its own live check. The tests behind this document are in [host/tests/spikes/fire_support](../host/tests/spikes/fire_support).

**Found while building, and not in the design above:**

- **The engine makes a hidden enemy at each aim point.** `doArtilleryFire` creates an `ArtilleryTargetE`, with no shape, on the side opposite the gun. For about 3 s the leader of the firing group knows it as an enemy. Once it's deleted, what's known of it is a place at the map's origin, so a firing squad reported a contact pointing at [0, 0]. Contacts now leave these out. See [spike_ghost_contact.py](../host/tests/spikes/fire_support/spike_ghost_contact.py). A firing group also goes to `COMBAT` for about 35 s, which is one more reason `in_combat` doesn't read behaviour.
- **Observers have to be spotters.** Naming any other station is refused, like a capability it doesn't have, and `commander_roster` shows `corrects_fire`.
- **Reports keep their order when a squad leaves a fight.** Those said out of combat used to go straight out, ahead of what was still queued from a moment before.
- **The review works out kills by shell from the records,** not from the `Killed` killer. A death within 60 m and 5 s of a shell landing is put down to that shell, which gives the gun and the mission, even when the killer is null. `kills.jsonl` is unchanged.
- **A radio row now records the sender's own grid.** Reports now hold grids of other things, such as `V1 is wrecked, grid 039 040`, which the belief map would plot as the sender's position. Older battles still go by the wording.
- **A known gap:** two orders to one station in the same second, such as a posture followed by a fire mission, both take effect, but only the last gets acknowledged. Both are in the order log.
