# Commander scenarios that test the commander

The scenarios so far test the harness: does each order work, and does each report come out right. These test the LLM. Each sets a problem where the right decision isn't the obvious one. The tools are only the means; the judgement is the subject.

Rules for all of them:

- **The briefing is intel, not truth.** It says what a real commander would be told, with real uncertainty ("a reinforced platoon, possibly more"). What the commander isn't told is listed under "Hidden" and never appears in any tool's output, except through what stations see and say.
- **Every run differs.** Each scenario lists what's drawn at random when it starts (direction, positions, timing), so a commander can't learn the answer, only the method.
- **Winning isn't the measure.** The review looks for the decisions listed under "Good play" and "Poor play". A loss caused by fog is a fair loss. A loss caused by a tool fault gets fixed.

## Summary

| # | Scenario | What it tests | Map | Harness today |
|---|---|---|---|---|
| 1 | Hold the crossroads | Early warning and repositioning against an attack from an unknown direction | Stratis | Needs a timed enemy assault and a "hold" objective |
| 2 | The hidden gun | Recon before the assault, and dealing with a threat nobody mentioned | Stratis | Needs crewed enemy weapons |
| 3 | Two roads | Route choice from the ground, scouting a defile | Stratis | Built: `llm_two_roads` |
| 4 | Pinned in the open | Saving the wounded under fire, smoke, and timing | VR or Stratis | Needs a "casualties evacuated" objective |
| 5 | The decoy | Not overcommitting to the first contact | Stratis | Built: `llm_decoy` |
| 6 | In and out | Tempo, and pulling out on time before enemy reinforcements arrive | Stratis | Needs timed reinforcements and a "destroy, then extract" objective |
| 7 | Two villages, one platoon | Using recon to choose where to commit, rather than splitting forces | Stratis | Needs objectives tied to one enemy group |
| 8 | Silence on the net | Noticing a station that's gone quiet, and acting on it | Stratis | Built: `llm_silence` |
| 9 | Guns only | Fire control: grids, adjusting fire, ammunition economy | Stratis | Built: `llm_guns_only` |
| 10 | Danger close | Air support with friendly troops near the target | Stratis | Built: `llm_danger_close`; better with the CAS talk-on |

---

## 1. Hold the crossroads

**Tests:** whether the commander covers the approaches before it knows the threat, keeps a reserve, and moves it once contact shows the real axis.

- **Setup.** Two infantry squads, a scout team and a mortar hold a crossroads village. Stratis, around Agia Marina or Agios Ioannis.
- **Briefing.** "An enemy attack is expected within the next 20 minutes. Its direction is unknown. Hold the village."
- **Hidden:**
  - The attack comes from one of three directions, drawn at random: a road, a ridge, or the coast.
  - Two squads, starting between T+8 and T+14.
  - In some draws, a small patrol probes a different direction a few minutes earlier, as a feint.
- **Win.** No enemy within 100 m of the crossroads at T+25.
- **Lose.** The village is taken, or every station is lost.
- **Good play:**
  - The scout team, or sentries, go on the ground that overlooks the approaches. `commander_ground` with `to` tells it what can be seen from where.
  - At least one squad is held back as a reserve.
  - The mortar is registered on likely approaches, with grids worked out in advance.
  - Once contact shows the main axis, the reserve moves there.
- **Poor play:**
  - All forces spread thinly on a perimeter.
  - Everyone committed to the feint.
  - No one watching a whole approach.
  - No timers set, so the first the commander hears is the assault itself.
- **Harness needs:**
  - **Timed enemy assault.** An enemy group that appears at a time, at one of several points, and attacks a place.
  - **Hold objective.** No enemy within a radius of a point at the end.

## 2. The hidden gun

**Tests:** whether the commander sends recon before committing the main force, and whether it deals with a threat nobody told it about. This is the owner's example.

- **Setup.** Attack an enemy camp on a hill: Camp Maxwell or the Air Station.
- **Forces.** Two squads, a scout team (a spotter) and a mortar with limited rounds.
- **Briefing.** "An enemy section holds the camp. Take it."
- **Hidden:**
  - An HMG or GMG emplacement covers the obvious approach, drawn from two or three firing positions.
  - In some draws there's a second, lighter one.
- **Win.** The enemy is cleared from the camp.
- **Good play:**
  - The scouts go forward first and report the gun.
  - It's marked with an honest confidence.
  - It's destroyed by mortar fire, adjusted by the scouts, or flanked from dead ground, before the squads cross its field of fire.
- **Poor play:**
  - Squads sent straight up the approach.
  - Contact reports from the gun ignored.
  - The mortar's rounds spent on the camp instead of the gun.
- **What to measure.** Friendly losses before the gun is silenced, and whether any station had eyes on it before the main force moved.
- **Harness needs.** Crewed enemy weapons: a static weapon or vehicle spawned with its own crew. Squads already report "vehicles" in sight.

## 3. Two roads

**Tests:** reading the ground before choosing a route, and scouting a defile instead of driving through it.

- **Setup.** Move a mounted platoon (two squads in two trucks) to a rendezvous 3 km away on Stratis. Two roads lead there:
  - a short one through a valley with high ground on both sides;
  - a longer one over open ground.
- **Briefing.** "Enemy activity has been reported in the area. Be at the rendezvous by T+20."
- **Hidden:**
  - An ambush party on the high ground over one road, sometimes the long one, drawn at random.
  - Sometimes no ambush at all.
- **Win.** At least six men at the rendezvous by T+20.
- **Good play:**
  - Reading the map and the ground tool.
  - Dismounted scouts sent along the valley's heights first.
  - On contact: getting off, suppressing, and recovering the wounded.
- **Poor play:**
  - Driving the short road blind.
  - Staying mounted under fire.
  - Leaving the wounded behind without saying so.
- **Harness needs.** A convoy-arrival objective that counts men rather than squads, a small extension of the "stations at a place" objective. Everything else exists.

## 4. Pinned in the open

**Tests:** triage under time pressure: using smoke and fire for cover, and choosing when to carry instead of rushing.

- **Setup.** A scout team is pinned in the open with two men down. An enemy MG on a rise 300 m away covers them.
- **Forces.** A squad 400 m back, a mortar with HE and SMOKE, a medic, and an aid post site.
- **Briefing.** "Viper is pinned with two casualties. Get them out."
- **Hidden:** the MG's exact position (the scouts give a bearing), and how long the wounded have.
- **Win.** Both wounded at the aid post alive.
- **Lose.** Both dead, or the rescuers wiped out.
- **Good play:**
  - The MG's grid worked out from the scouts' bearing and range.
  - A smoke screen between the MG and the casualties, then HE on the MG.
  - Carriers sent under cover of the smoke, and the aid post set up nearby.
- **Poor play:**
  - Carriers sent straight across the MG's line.
  - Fire called on a guessed grid with no observer.
  - Waiting too long.
- **Harness needs.** An objective that the named casualties reach a place, or an aid post, alive. Knocked-down casualties and smoke already exist.

## 5. The decoy

**Tests:** handling hypotheses, and not chasing the first thing it sees.

- **Setup.** Clear a village on Stratis (Girna or Agia Marina) with two squads and a scout team.
- **Briefing.** "An enemy platoon is believed to be in the area of the village."
- **Hidden:**
  - A visible patrol moves in the open fields 600 m from the village, placed to be seen first.
  - The main body is garrisoned in the village.
- **Win.** The village cleared.
- **Good play:**
  - The patrol is marked as a hypothesis ("not the main body?").
  - One element screens it while the main effort stays on the village.
  - Markers are updated as reports come in.
- **Poor play:** both squads chase the patrol across the fields, and the village is left alone until time runs short.
- **Harness needs:** none. Patrol and garrison enemies exist.

## 6. In and out

**Tests:** tempo, timed coordination, and leaving on time.

- **Setup.** Destroy an enemy supply truck parked in a hamlet, then get back to the pick-up point.
- **Forces.** Two squads and a scout team.
- **Briefing.** "Expect an enemy quick reaction force within about 15 minutes of the first shot."
- **Hidden:**
  - The reaction force arrives 10 to 18 minutes after first contact, drawn at random.
  - It comes from one of two directions.
  - It outnumbers the commander's force.
- **Win.** The truck destroyed, and at least half the force at the pick-up by T+30.
- **Good play:**
  - The raid planned with timed orders and chained legs.
  - A screen on the reaction force's likely approaches.
  - The withdrawal begun as soon as the truck burns, with the wounded carried.
- **Poor play:**
  - Lingering to clear the hamlet.
  - No watch on the approaches.
  - Leaving the wounded behind.
- **Harness needs:**
  - Reinforcements triggered by first contact, or at a time.
  - A "vehicle destroyed" objective.
  - Objectives that must be met in order (destroy, then extract).

## 7. Two villages, one platoon

**Tests:** economy of force. It asks whether the commander recons both, picks one, and masses on it, rather than splitting into two weak attacks.

- **Setup.** Two villages to clear, 1.5 km apart, with two squads, a scout team and a mortar.
- **Briefing.** "Both villages are reported held. Clear both by T+40."
- **Hidden:** which village is lightly held (three men) and which strongly held (ten men with a gun), drawn at random.
- **Win.** Both cleared.
- **Good play:**
  - Scouts look at both first.
  - The weak one is taken with one squad, or the strong one with everything plus the mortar.
  - Then the other.
- **Poor play:** one squad sent to each at once, and both attacks stall.
- **Harness needs:** an objective tied to one enemy group ("clear the enemy at Girna"), rather than all enemies.

## 8. Silence on the net

**Tests:** monitoring discipline: noticing a station that's gone quiet, without being told, and doing something about it.

- **Setup.** Two squads hold a long line of observation posts, three small teams spread over 2 km, during a quiet period.
- **Briefing.** "Watch the valley and report movement. Higher expects a sitrep every 10 minutes."
- **Hidden:**
  - At a random time, one post is silently overrun.
  - An enemy patrol then moves through its sector.
- **Win.** The patrol located and engaged before it reaches the rear area.
- **Good play:**
  - A repeating check-in is scheduled.
  - The missed check-in is noticed, someone is sent to look, and the gap is covered.
- **Poor play:**
  - No check-ins.
  - Silence taken as "all quiet".
  - Finding out only when the patrol hits the rear.
- **Harness needs:** none. Overdue check-ins are shown in the briefing, and a scenario event can take out a station.

## 9. Guns only

**Tests:** fire control on its own: grids from bearings, adjusting fire, and conserving ammunition.

- **Setup.** An enemy section dug in at a farm.
- **Forces.** An observer team (a spotter) on a hill 800 m away, and a mortar with 12 HE and 4 smoke. No infantry assault is possible.
- **Briefing.** "Destroy the enemy at the farm with the mortar. There's no resupply."
- **Hidden:** exactly where in the farm they are, drawn from three layouts.
- **Win.** The enemy at the farm all dead or down.
- **Good play:**
  - The target grid worked out from the observer's bearing and range.
  - One round to adjust, with corrections from the splash reports.
  - Fire for effect only once it's on target.
  - No rounds wasted on old grids.
- **Poor play:**
  - All 12 rounds fired at the first guess.
  - Splash reports ignored.
  - Corrections in the wrong direction.
- **Harness needs:** none.

## 10. Danger close

**Tests:** using air support safely with friendly troops in contact, giving clean grids, and timing the strike with the assault.

- **Setup.** A friendly squad in contact 150 to 250 m from an enemy position on a hill. A Blackfoot is on call.
- **Briefing.** "Bravo is in contact. Hawg is on station. Break the enemy on the hill."
- **Hidden:** the enemy's exact position, and that a second enemy group sits behind the crest.
- **Win.** The enemy on the hill cleared without losses to the strike.
- **Good play:**
  - Bravo's position confirmed first.
  - The CAS grid set clear of Bravo, with a small radius.
  - Bravo held or pulled back during the run, then sent in straight after it.
- **Poor play:**
  - CAS called on Bravo's own grid, or with a large radius.
  - Bravo moving into the strike area.
  - No follow-up after the run.
- **Harness needs:** none, though the CAS talk-on (`docs/COMMANDER_CAS.md`) would make it fairer when the enemy has gone to ground.

---

## Built so far

- **Random draws** (`scenario.draw`): any value may be `{one_of: [...]}`, `{between: [lo, hi]}` (numbers or times) or `{around: grid, within_m: m}`. Things drawn together go under `variant: {one_of: [...]}`, where each choice is a bundle of entries added to the scenario's lists. They are drawn once when the battle starts, from a seed (`commander start --seed N` replays a battle), and the seed and every draw are kept in `battle.json`.
- **Losing conditions**: `failure: {casualties_pct: 40}` (that share of the starting strength dead or down at once), `failure: {critical: [Recon, V1]}` (a station with every man dead, or a vehicle destroyed), alongside `all_stations_lost`. The briefing states them under "THE MISSION FAILS IF", and `commander_mission` lists them as `fails_if`, written from the same settings the harness checks. A failure ends the battle with "MISSION END. Mission failed: ..." to the commander.
- **Men at a place**: `success: {men: 10, within_m: 150, of: grid}`, counting soldiers rather than squads.
- **Positions checked on the terrain**: every observer, ambush site and hiding place in the built scenarios was checked with the terrain sample (line of sight, water) before it was written.

## What these need from the harness

In order of how many scenarios each one unlocks:

| Need | Unlocks | Size |
|---|---|---|
| Timed or triggered enemy movement: appear at a time or on first contact, at one of several points, and attack a place | 1, 6, 8 | medium |
| Crewed enemy weapons: a static gun or vehicle with its own crew | 2, 7 | small |
| More objective kinds: hold an area until a time, a vehicle destroyed, named casualties evacuated, one enemy group cleared, objectives in order | 1, 4, 6, 7 | medium |
| CAS talk-on | 10 | small |

Scenarios 3, 5, 8, 9 and 10 are built. The rest wait on the needs above.

## Measuring

Beyond win or lose, the records already hold what's needed to score the decisions above:

- **Time to first eyes on each enemy group:** contact reports matched to truth.
- **Whether recon came before the main effort:** order times per station.
- **Losses before and after a threat was found:** the kill log against the time of the first report of it.
- **Rounds per hit:** fire missions, splash reports and kills.
- **Silence noticed:** the time from a missed check-in to the commander's first order or question about that station.
- **Hypotheses kept honest:** markers created and retired, against what was true.

A short per-scenario rubric in the review page, built from these, would let runs be compared across models and doctrine changes.
