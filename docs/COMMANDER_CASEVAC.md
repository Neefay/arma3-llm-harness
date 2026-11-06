# Commander Mode: CASEVAC design

**Status:** design only. Nothing here is in the main system. The measurements come from throwaway tests on a headless dedicated server with ACE, on Arma 3 2.22, on the flat open ground of the VR map, in [host/tests/spikes/casevac](../host/tests/spikes/casevac). Written 2026-11-06. It extends [COMMANDER.md](COMMANDER.md).

## 1. Summary

A soldier hit under ACE either dies or goes down unconscious. The ones who go down lie where they fell, ignored by the enemy, on a clock of a few minutes. The commander can leave them, or send a medical team to carry them to a vehicle or an aid post, and get them back in the fight. Every step is exposed to real fire.

The risky question has an answer: **an AI can move a casualty**. ACE's own carry can't do it, but a hidden dummy unit doing the walking can, in the proper animations.

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
- **19 of those 28 were dead by 6.3 minutes.** The source says enemies don't target a downed man, so most of that is probably bleeding out, though this test can't tell them apart.
- So ACE's defaults already give what's wanted, and **no extra chance of death is needed**. If more is ever wanted, a handler on `ace_unconscious` works: at 50% it killed 5 of 12. `ace_medical_deathChance` does nothing for AI.

Twelve men given one body wound each, untreated, lasted longer: the first death came at 6:16, and at 8:15 three were dead, four in cardiac arrest and two still alive and awake or close to it. Real gunfights do more damage than one wound, so the clock to plan around is **about 3 to 6 minutes**.

### 2.4 Under fire

A rescue in the open at 130 m, in plain view of 4 enemies, with a medic set to CARELESS:

- Enemies knew about the medic within about 15 s of the drag starting, and **both men were dead about 25 s after it began**. So rescue under fire is as dangerous as it should be.
- The source says a downed man is hidden from enemies, not made captive. In this test no enemy knew about him while he was down, but he **woke up** during it, having no wound, and was shot awake. So "they ignore the downed" is only partly confirmed, and hits on a carried body aren't measured.

### 2.5 AI medics and leaders

- **ACE's AI medic works:** a medic in the group was on the casualty in 10 s, and had the bleeding stopped in about 20 s. It stayed about a minute, then went back to formation. It only serves its own group, needs the Medic trait, and from the source waits for about 30 s since that unit last fired or was hit. It never moves a casualty.
- **Waking up:** from the source, a stable casualty has a 10% chance every 15 s, so about 150 s on average. So a treated man can get up without ever seeing an aid post.
- **A leader going down:** command passes by itself, and the squad obeyed a new order at full speed, leaving him behind.
- **A leader waking up takes command back,** and the squad **ran back to him**, 40 m in 10 s. That would pull a squad off its objective unasked, so it needs handling.

## 3. What changes for the harness

These are needed whatever the orders look like:

| Today | With ACE |
|---|---|
| `alive` means effective | Downed men are alive. The packet, "N of M effective" and truth all have to count them apart |
| `enemy_cleared` means none alive | Downed enemies are alive, so a battle might never end. Downed has to count as out |
| Everyone in a group moves with it | Downed men stay where they fell, and the squad moves on. It has to say so |
| ACE's AI medic | It overrides orders with `doMove` and `forceSpeed 0`, so a man being carried or carrying has to be opted out, with `ace_medical_ai_lastFired` |
| Leader wakes | Keep command with whoever has it, or the squad runs back to him. Not yet tested |
| ACE required | It's a separate profile, `commander_ace`, and scenarios without it aren't affected |

ACE's settings can be set per mission, with `cba_settings.sqf`, so this doesn't change anyone's own server.

## 4. Proposed design

### 4.1 Reports

Only what a squad could say. No body counts for anyone else's squad, and no vital signs.

```text
Reed's down.                                      (PRIORITY)
Reed's dead.                                      (when it's known. A squad that moved on doesn't know)
Reed's down, about 80 m south-west of us. We've left him.    (when a squad moves away from him)
6 of 8 effective, 1 down, 1 dead.                 (strength)
Reed's back on his feet.
```

A new question topic, `casualties`, gives each one known to that squad. Casualties get ids on the commander's own list, as vehicles do (`C1`, `C2`), with the place last reported, which may be old. Nobody reports a grid under fire, so the commander has to work it out from a bearing and range, as with contacts.

### 4.2 Orders

| Order | What it does |
|---|---|
| `RESCUE` | A medical station goes to casualty `C1` or a grid, finds him if he's within a short distance, picks him up, and carries him to a grid, a vehicle `V1` or an aid post `A1` |
| `TREAT` | A medical station goes to a casualty and treats him where he lies |
| `AID_POST` | A medical station sets up a tent at a grid, which takes a while |

- A station gets these through its capabilities, and needs a Medic-trait soldier. Squads with a medic also treat their own without being told, as ACE does.
- **Failures come over the radio,** as with fire missions: `Can't find him.`, `Unable, no medic.`, `He's gone.`, `V1 is full.`, and the medic team's own casualties.
- **The carry** is the dummy method. If the dummy stops making progress for a few seconds, it falls back to the owner's method, so an awkward spot can't leave a medic stuck: stop, play the long animation, and load or place him.

### 4.3 The aid post

A real tent, in the world, that can be seen and destroyed. A downed man carried to it, with a medic there, is healed by `fullHeal` after a set time, proposed at 60 s, one at a time per medic. He then runs back to his squad on foot, which is what the engine already does. Field treatment stays at ACE's own pace.

### 4.4 Getting back

Stage one is that a healed man runs to his squad by himself, across whatever's in between, and that's a risk the commander can see coming. If his squad is gone, he joins the medical station. Ferrying men back by vehicle needs a way to detach and attach individual men, which orders can't do today, because they're given to a whole group. So that's stage two.

### 4.5 Records and review

The review gets casualties on the maps, a downed marker distinct from a death, and rescues on the timeline. Deaths say whether he died outright or after lying there, and how long for.

## 5. Build order

1. **ACE profile, and counting the downed:** effective strength, `enemy_cleared`, truth, and leader handling, with reports for going down. Existing scenarios run under it.
2. **The carry, in the game, by script:** with the fallback, tried among the village's buildings, and looked at through a game window.
3. **`RESCUE` and `TREAT`,** with the casualty list and its reports.
4. **`AID_POST`.**
5. **Records and review, then a scenario, doctrine and a real LLM run.**

## 6. Still unknown

- Whether the carry looks right to someone watching.
- Whether the dummy can get through the village: doors, walls and slopes.
- Whether a carried body takes hits, and what happens when the carrier is killed mid-carry. It should be easy for our own controller, and it's untested.
- Keeping command with the new leader when the old one wakes.
- Whether ACE changes how long battles take, or how the AI fights.
- The cost of ACE on the server with 40 men.

## 7. Decisions for the owner

1. **Carry or drag?** Proposed: carry, because it's quicker and one behaviour is simpler. A drag is lower to the ground, so it could be added for short moves under fire.
2. **Extra chance of death?** Proposed: none, because ACE's defaults already kill 36% outright and most of the rest within 6 minutes.
3. **Who treats?** Proposed: the scenario decides. A dedicated medical team with the capabilities above, with medics in squads being optional.
4. **How strong is the aid post?** Proposed: 60 s per man, built in about a minute, and one per team, to be tuned by playing.
5. **Getting back:** proposed: running back alone at first, and ferrying as a second stage.
