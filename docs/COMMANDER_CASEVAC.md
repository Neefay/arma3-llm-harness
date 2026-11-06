# Commander Mode: CASEVAC design

**Status:** built, and passing live on a headless dedicated server with ACE, through the commander's tools with a script in place of the LLM. No LLM has played it yet, and nobody has watched all of it in a window. The review page doesn't show it yet. Written 2026-11-06. It extends [COMMANDER.md](COMMANDER.md). The tests behind the measurements are in [host/tests/spikes/casevac](../host/tests/spikes/casevac).

## 1. Summary

A soldier hit under ACE either dies or goes down unconscious. The ones who go down lie where they fell, on a clock of a few minutes. The commander can leave them, have their squad carry them to a vehicle or a place, send medics to treat them where they lie, or set up an aid post and bring them to it. A treated man gets up and goes back to his squad.

**An AI can move a casualty.** ACE's own carry can't do it, but a hidden dummy unit doing the walking can, in the proper animations.

## 2. What was measured

### 2.1 Moving a casualty

| Method | Result | Verdict |
|---|---|---|
| ACE's `startDrag` and `startCarry` | The event handlers are registered only on machines with an interface, so on a dedicated server nothing happens, and the casualty stays claimed. From the source | Unusable as is |
| ACE's `startCarryLocal`, called directly, then `doMove` | Picks him up in 7 s with the right animations, then **never moves**: 0 m in 30 s | Dead end |
| Antistasi's drag: medic and casualty attached to a hidden dummy, which does the walking | 40 m in about 35 s (1.2 m/s), in the drag animations, and it stops at the destination. Letting go works, and the medic carries on normally | **Works** |
| The same idea as a carry: the medic in ACE's carrying animation, on a dummy | 53 m in 30 s (1.8 m/s), with the casualty on the shoulder, and the animation states are the right ones | **Works**, and it's quicker |
| Plain attach to a medic who walks as normal | 80 m in 20 s at a full run, in his rifle animation, then he went back to formation | Works, and it looks wrong |
| The owner's fallback: walk to the body, long animation, `loadPerson` | Arrived to within 2.2 m, played `AinvPknlMstpSlayWrflDnon_medicOther`, and the casualty was in the vehicle | **Works** |

Nobody has looked at these yet. The animation names are right, but only someone watching can say whether they look right. None was tried among buildings, where the dummy's pathing and the attached bodies are the risk.

### 2.2 Vehicles and healing

| Test | Result |
|---|---|
| `ace_common_fnc_loadPerson` into a vehicle driven by the same squad | In the cargo seat, and still in his group |
| The same into an **empty** vehicle | In the cargo seat, but **moved to a new group** until unloaded, so he'd vanish from his squad's roster meanwhile |
| Driving 200 m with him aboard | No damage, and he stayed in |
| `ace_common_fnc_unloadPerson` | Out, still unconscious, back in his group, in the `deadstate` pose |
| `Land_MedicalTent_01_MTP_closed_F` placed by script | Counts as a facility straight away, with him 6 m away |
| `ace_medical_fnc_fullHeal` | Up and healthy at once. He then ran back to his squad by himself, at 18 km/h, over about 190 m |

**A facility doesn't make treatment faster.** From the source, it only decides where a personal aid kit can be used. "Much faster at the tent" is something we'd script.

### 2.3 How men go down

Three firefights of 12 against 12 in the open, at ACE's defaults, with no medics:

| After | Standing | Down | Dead |
|---|---|---|---|
| About 3.5 minutes | 29 | 19 | 24 |
| About 6.3 minutes | 29 | 8 | 35 |

- Of the 44 men hit, **16 died outright (36%)** and **28 went down (64%)**.
- **19 of those 28 were dead by 6.3 minutes.** The number standing didn't change between those two counts, and the source says enemies don't target a downed man, so most of that is probably bleeding out, though this test can't tell them apart.
- So ACE's defaults already give what's wanted, and **no extra chance of death is needed**. If more is ever wanted, a handler on `ace_unconscious` works: at 50% it killed 5 of 12. `ace_medical_deathChance` does nothing for AI.

Twelve men given one body wound each, untreated, lasted longer: the first death came at 6:16, and at 8:15 three were dead and seven of the other nine were still down, four of them in cardiac arrest. Real gunfights do more damage than one wound, so the clock to plan around is **about 3 to 6 minutes**.

### 2.4 Under fire

A rescue in the open at 130 m, in plain view of 4 enemies, with a medic set to CARELESS:

- Enemies knew about the medic within about 15 s of the drag starting, and **both men were dead about 25 s after it began**. So rescue under fire is as dangerous as it should be.
- The source says a downed man is hidden from enemies, not made captive. In this test no enemy knew about him while he was down, but he **woke up** during it, having no wound, and was shot awake. So "they ignore the downed" is only partly confirmed, and hits on a carried body aren't measured.

### 2.5 AI medics and leaders

- **ACE's AI medic works:** a medic in the group was on the casualty in 10 s, and had the bleeding stopped in about 20 s. It stayed about a minute, then went back to formation. It only serves its own group, needs the Medic trait, and from the source waits for about 30 s since that unit last fired or was hit. It never moves a casualty.
- **Waking up:** from the source, a stable casualty has a 10% chance every 15 s, so about 150 s on average. So a treated man can get up without ever seeing an aid post.
- **A leader going down:** command passes by itself, and the squad obeyed a new order at full speed, leaving him behind.
- **A leader waking up takes command back,** and the squad **ran back to him**, 40 m in 10 s. That would pull a squad off its objective unasked, so it needs handling.

### 2.6 Reaching a man

The first person to watch the carry found a medic who never moved, and it took some finding. With a body at some spots in a house, nowhere in or right beside that house can be planned to, though it's fine with the body elsewhere, and open ground is fine either way. A man told to go there stands still with `MOVE` as his command for about 12 s, then reports himself ready. It isn't the group, ACE's AI medic, or the body being below the floor, all of which were tried.

So a rescuer tries the house's nearest position at the man's level, the man himself, then a ring 25 m out (14 m wasn't enough), nearest him first. A man stalled within 8 m has arrived. If he's as close as he can get, or he's out of places to try within 60 m, he works for 8 s, and the man is then with him. That's the owner's hack, and it's only used when walking there has failed.

The headless check passed while the demo failed for its first viewer, for two reasons worth keeping in mind: it read the server's state, so it couldn't see that `switchMove` hadn't reached the client, and it didn't pause, so it didn't catch what a pause changes.

### 2.7 The carry as built

`brmh_cmd_fnc_startCarry` in [commander_boot.sqf](../host/src/arma_harness/adapters/commander_boot.sqf) is the controller, and [demo_carry.py](../host/tests/demo_carry.py) shows it, with `--check` to run headless as a test.

| Scene | Result |
|---|---|
| In the open, 100 m | About 8 s to reach him, 9 s to lift, and about 1.7 m/s |
| Around a house, then into a truck or Hunter | Goes round with no help, and he's in the cargo seat, still in his group |
| Out of a house | By whichever way above works. About 75 s for 65 m |
| The dummy stuck on the way | Gives up after 8 s, the man works on him for 8 s, then he's put at the place, if it's within 60 m |
| The carrier killed or downed | Lets go at once, and the casualty lies there, still alive |
| The casualty killed | Lets go at once, and the carrier goes back to his squad |

## 3. What changed for the harness

| Before | With ACE |
|---|---|
| `alive` meant effective | A downed man is alive and no use. Strength, truth, boarding, clearing, cordons and sight checks all count him out |
| `enemy_cleared` meant none alive | Downed counts as out, so a battle ends. Truth holds where they are |
| A squad moved together | Downed men stay where they fell, and the squad says so if it's left one |
| A leader who wakes took command back | His squad would run back to him. Whoever's got it now keeps it |
| ACE's AI medic | **Off** for this mission, in [cba_settings.sqf](../missions/brmh_commander.VR/cba_settings.sqf). It orders medics about every 10 s, over ours. So nobody's treated unless the commander orders it |
| ACE required | It's a separate profile, `commander_ace`, chosen by a scenario's `mission`. Scenarios without it are unaffected, and all still pass |

## 4. The commands

### 4.1 Reports

Only what a squad could say. No vital signs, and no grids in a fight.

```text
Owen King's down, grid 060 060. Listed as C1.     (PRIORITY. No grid in a fight)
Found Owen Taylor down, grid 058 060. Listed as C2.   (someone else's, within 30 m, if nobody had listed him)
We've left Matthew Young, about 150 m north of us.
Owen King's dead.                                 (only if the squad was near enough to know)
Owen King's back on their feet.
4 of 6 effective, 2 down.                         (strength)
C1 Owen King, down, about 40 m east. C2 Callum Roberts, down, on V1.     (the casualties topic)
```

The commander's list of casualties, with the place each was last reported, is in `commander_mission` and every briefing. It can be out of date.

### 4.2 Orders

All four stand alone, need the capability, and leave the rest of the squad's orders as they are.

| Order | Takes | What it does | What's said |
|---|---|---|---|
| `CARRY` | `casualties`, and `vehicle` or `at` (a place or an aid post) | One free man each picks up a casualty, nearest first and the leader last. With no list, everyone down within 100 m. At a post they're set down about 11 m clear of it, because bodies against the tent couldn't be reached | `Got Owen King, on the way.` `Owen King's loaded.` `Set Owen King down.` |
| `UNLOAD` | `vehicle`, `casualties` | Takes them off a stopped vehicle, if the squad has someone within 25 m | `Owen King's off V1.` `V1 has to stop first.` `Unable, nobody at V1.` |
| `TREAT` | `casualties` | Each medic takes one at a time. Early on he stops getting worse, and at the end he gets up | `Treating Owen King.` `Owen King's back up.` `Unable, no medic here.` `Can't find Owen King.` |
| `AID_POST` | `at` | A medic goes there and sets up a real tent, which goes on the list as `A1`. Shells landing within 20 m can destroy it, in about three close rounds. Vehicles and bullets can't: AI drivers don't avoid it, and a truck leaving the rendezvous flattened it | `Setting up the aid post.` `Aid post up, grid 040 060. Listed as A1.` |

`DISMOUNT` leaves the downed in their seats, and they don't count towards `MOUNT`. A man's whereabouts for an order come from the commander's list, so someone sent to an old report more than 150 m out says `Can't find`.

### 4.3 Where treatment's fast

A scenario sets `medical: { field_s, facility_s, build_s }`, with defaults of 120, 60 and 60. `facility_s` applies within 30 m of an aid post or 15 m of a medical vehicle, which is one whose class says so, such as the HEMTT Medical, or a scenario's `medical: true`. A man aboard a medical vehicle can be treated without coming off. ACE itself makes nothing faster for being in a facility, so this is ours. A station's `medics: 2` gives two of its men ACE's flag.

### 4.4 Men who end up away from their squad

Your fourth question. A man stays in his squad's group the whole time, wherever he is, carried, on a truck, or at a post, so nothing about the roster changes.

- **On his way:** his squad can see him on its own truck. If he's left behind, it says so once, and it can't tell what happens to him afterwards. Other squads that come within 30 m find him.
- **Treated:** he runs back to his squad by himself, however far. That's a risk the commander can see coming. `MOUNT` picks him up if he's within 500 m of the vehicle.
- **His squad's gone:** he joins whoever treated him, and says so: `Owen Taylor's with us now. There's nobody left to go back to.`
- **Ferrying him back on his own isn't possible yet.** Orders go to a whole group, so a man can't be told to board a truck apart from it. As you said, that's for later.

### 4.5 Your plan, as orders

[casevac_rv.yaml](../scenarios/commander/casevac_rv.yaml) is the scenario, with short treatment times, and `play_casevac` in [live_commander.py](../host/tests/live_commander.py) plays this through the commander's tools:

```text
T+00:20  two of Alpha's six go down, by a scenario event
Alpha    CARRY C1 C2 to V1         two men carry, about 70 s for 100 m, loaded
Alpha    MOUNT V1, MOVE 040 060    the other four board, and they drive there
Angel    MOUNT V2, MOVE 040 060, DISMOUNT, AID_POST 040 060
Alpha    DISMOUNT                  the casualties stay in their seats
Alpha    UNLOAD V1
Alpha    CARRY C1 C2 to A1, then SENTRY 040 060
Angel    TREAT C1 C2               both up in about 30 s
Alpha    MOUNT V1                  all six, and MOVE 070 060, DISMOUNT
         OBJECTIVE COMPLETE, at about T+09:40
```

### 4.6 Other cases that pass live

`play_casevac_cases`, on [casevac_cases.yaml](../scenarios/commander/casevac_cases.yaml): treating in the field, taking 35 s with `field_s` at 25; treating aboard a medical vehicle, 19 s with `facility_s` at 10; a man whose squad's been wiped out joining his medics; a leader going down and his squad obeying the man who took over, who keeps command when he wakes; a carry while the rest of the squad moves off; and a man left behind.

## 5. What isn't done

1. **The review page** doesn't show casualties yet: no markers for the downed, no rescues on the timeline, and deaths don't say whether a man lay there first. The records have what it needs, in `truth` and `radio`.
2. **A real LLM run,** and a fight with an enemy shooting at the rescuers. All of the above has no enemy in it.
3. **Ferrying individuals,** by detaching men from their group.

## 6. Still unknown

- **How it looks.** The owner has seen the carry, and saw the body-on-the-ground bug, which is fixed but hasn't been looked at since. Nobody's watched treating, or a man being loaded.
- **Whether a carried body takes hits.** A rescue in the open at 130 m got both men killed within about 25 s, as it should, but which rounds hit whom isn't clear.
- **Getting through a real town.** The village has seven buildings, and the VR map is flat. Doors, walls and slopes elsewhere haven't been tried.
- **The cost of ACE on the server** with 40 men, and whether it changes how long battles take.

## 7. Decisions

Made by the owner, 2026-11-06:

1. **Carry only,** by the dummy method, and no drag for now.
2. **No extra chance of death.** ACE's defaults stand.
3. **Who treats:** any soldier with ACE's medic flag. Who has one is up to the scenario. In the event ACE's AI medic had to go off, so they only treat when ordered.
4. **The aid post:** about a minute to build, 60 s to heal each man, and one per team. A scenario sets these, because testing needs them much faster.
5. **Getting back:** running back alone is fine for now, with ferrying as a later stage.
