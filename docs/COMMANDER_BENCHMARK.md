# Commander benchmark

How to run the commander scenarios with a real LLM so that runs, and models, can be compared fairly, and how to read the results. The scenarios' designs, and what good and poor play look like in each, are in [COMMANDER_SCENARIOS.md](COMMANDER_SCENARIOS.md). How a battle works is in [COMMANDER.md](COMMANDER.md).

## Contents

1. [What the benchmark is](#1-what-the-benchmark-is)
2. [Before the first run](#2-before-the-first-run)
3. [The protocol](#3-the-protocol)
4. [Running one battle](#4-running-one-battle)
5. [Reading the results](#5-reading-the-results)
6. [What the numbers can and can't tell you](#6-what-the-numbers-can-and-cant-tell-you)

## 1. What the benchmark is

Six scenarios on Stratis, each played on the same six seeds by every model. The seeds are in [scenarios/commander/benchmark.yaml](../scenarios/commander/benchmark.yaml). A seed fixes everything the commander isn't told: where the enemy is, and what happens when. So every model faces the same hidden situations, and each scenario's six seeds cover its hidden variants evenly. A test (`host/tests/test_benchmark.py`) checks every seed still hides what that file says, so an edit to a scenario can't silently change what a seed means.

The scenarios, as built (where these differ from the designs in COMMANDER_SCENARIOS.md, the files are what's played):

| Scenario | Tests | Win | Lose | Time | What the seeds vary |
|---|---|---|---|---|---|
| `llm_hidden_gun` | Recon before the assault, and a threat nobody mentioned | The enemy cleared, gun crews included | Half the force dead or down | 30:00 | The HMG at one of 3 spots; a second gun or not |
| `llm_two_roads` | Route choice from the ground, scouting a defile | 10 men within 150 m of grid 036 029 | Half the force dead or down | 25:00 | An ambush on the western track, the eastern track, or none |
| `llm_decoy` | Not chasing the first contact | Every enemy cleared, garrison and patrol | Half the force dead or down | 30:00 | Where the patrol starts |
| `llm_silence` | Noticing a station that has gone quiet | The raiders cleared | Half the force dead or down | 30:00 | Which post is silenced, and when (T+6 to T+10) |
| `llm_guns_only` | Fire control: grids, adjusting, ammunition | The enemy section cleared, by the mortar (12 HE, 4 smoke, no resupply) | Eyes, the observers, lost | 20:00 | Which of 3 spots the section holds |
| `llm_danger_close` | Air support with friendly troops 200 m from the target | The enemy on the hill cleared | 40% of the force dead or down | 20:00 | Nothing: six repeats of one battle |

All six are on the `commander_stratis` profile, so ACE isn't needed. All six use `hold` mode: messages that arrive during a turn wait for the next one.

## 2. Before the first run

1. **Build and deploy @brmh.** The commander's broadcasts are handled by @brmh since PR #1, so an older build leaves carried men's poses unseen and the observer chat empty. With no game running:

   ```powershell
   & "C:\projects\other\arma-harness\host\.venv\Scripts\python.exe" "C:\projects\other\arma-harness\tools\build.py"
   ```

2. **Claude Code with a subscription login.** Commander mode wakes the session through Claude Code channels, which need a claude.ai or Console login. Clear `ANTHROPIC_API_KEY` in the shell you launch from, or some modes bill API credits instead:

   ```powershell
   Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
   ```

3. **Check the lockdown** once per Claude Code version. It proves the commander's session gets only its own tools, and it uses one small model call:

   ```powershell
   & "C:\projects\other\arma-harness\host\.venv\Scripts\arma-harness.exe" commander check-lockdown
   ```

   It fails on any tool the session shouldn't have. Don't run a benchmark on a version that fails it.

## 3. The protocol

The rules that make runs comparable:

- **Same seeds for every model.** Play each scenario on the six seeds in `benchmark.yaml`. A shorter pass that still covers every variant: hidden gun 2, 1, 5, 116, 7, 40 (all six), two roads 1, 7, 5, decoy 1, 3, 5, silence 1, 7, 5, guns only 1, 5, 7, danger close 1, 2, 3.
- **One fresh session per battle.** Start a new Claude Code session for each battle and close it when the battle ends. A session that carries over remembers the last battle.
- **Nobody talks to the commander.** After typing `start`, don't send it anything. Its only input is the radio. Watching is fine (`--watch` opens a game window in the observer slot, and it can't help the commander), but don't intervene.
- **The same doctrine for every model.** It's `host/src/arma_harness/commander/doctrine.md`, delivered by the server. Changing it is a different experiment: run every model again.
- **Only finished battles count.** A battle that ends "unfinished" was cut short by the session or the game, not by the commander's play. Run that seed again.
- **Nothing else on the game.** Don't run spikes, other scenarios or anything else against the running game during a battle.

**Time.** A battle lasts until its objective is met, it's lost, or its time limit, so at most 20 to 30 minutes. The full set is 36 battles per model, roughly 12 to 15 hours. The shorter pass is 18.

**Usage limits.** A commander session costs model calls on every wake, so a long battle uses a fair share of a subscription's limits. If the limit is reached mid-battle, the commander stops answering and the battle plays out without it. That battle doesn't count.

## 4. Running one battle

1. **Set it up.** This boots the game if it isn't running, places everything, and prints the launch command:

   ```powershell
   & "C:\projects\other\arma-harness\host\.venv\Scripts\arma-harness.exe" commander start llm_hidden_gun --seed 116
   ```

   Repeating `start` with another scenario or seed reuses the running game and clears the last battle.

2. **Launch the commander** from its workspace, a locked-down folder outside the repo. Name the model to benchmark:

   ```powershell
   Set-Location "C:\Users\ianri\AppData\Local\arma-harness\commander\workspace"
   & claude --model opus --dangerously-load-development-channels server:commander
   ```

   Use the model names the `claude` CLI takes (`opus`, `sonnet`, `haiku`, or a full model id). The battle record reads the model actually used from the session transcript.

3. **Type `start`** in the session. The commander loads its tools, reads its mission, and plays. Every later turn is started by the radio or by its own timers.

4. **Wait for the end.** The session receives "MISSION END" with the reason: objective achieved, mission failed, or time limit. To follow along without touching anything:

   ```powershell
   & "C:\projects\other\arma-harness\host\.venv\Scripts\arma-harness.exe" commander status
   ```

5. **Close the session** (`/exit`), and start the next battle with step 1.

6. **When you're done for the day**, shut the game down:

   ```powershell
   & "C:\projects\other\arma-harness\host\.venv\Scripts\arma-harness.exe" commander stop
   ```

Records go to `C:\Users\ianri\AppData\Local\arma-harness\runs\<run>\commander-<n>\`, one folder per battle, with the seed and what it hid in `battle.json`.

## 5. Reading the results

**All battles of a scenario, side by side:**

```powershell
& "C:\projects\other\arma-harness\host\.venv\Scripts\arma-harness.exe" commander compare llm_hidden_gun
```

**Every measure, one row per battle, for a spreadsheet** (one file per scenario):

```powershell
& "C:\projects\other\arma-harness\host\.venv\Scripts\arma-harness.exe" commander compare llm_hidden_gun --csv > "C:\Users\ianri\Documents\llm_hidden_gun.csv"
```

`compare` takes every finished battle of the scenario, scripted tests included (their model reads "Scripted"), so filter on `model`. `--battle RUN:ATTEMPT` picks battles by hand instead.

**One battle, replayed:** `commander review --run RUN --attempt N` writes a page that puts the commander's picture beside the truth, with the timeline, radio log, orders and the commander's own words. `commander site --out FILE --battle RUN:ATTEMPT=Label ...` puts several on one page to share. See COMMANDER.md, section 15.3.

### The columns

| Column | Meaning |
|---|---|
| `battle`, `scenario`, `model` | Which battle (`RUN:ATTEMPT`), which scenario, and the model that commanded, from the transcript |
| `seed`, `hidden` | The seed, and what it hid. Battles with the same `hidden` faced the same situation |
| `outcome` | `won`, `failed`, `time limit` or `unfinished` (see section 3) |
| `ended` | The exact words of the end |
| `duration_s` | Mission time to the end |
| `friendly_lost`, `friendly_total` | Men dead or down at the end, of the force's starting strength |
| `enemy_killed`, `enemy_total` | The same for the enemy. Strength comes from the battle's truth record, so a gun counts its real crew |
| `first_contact_s` | When any station first reported a contact |
| `turns`, `orders`, `questions` | How many turns the commander took, orders it sent and questions it asked |
| `enemy_markers`, `marker_error_m` | Enemy markers it placed, and on average how far each was from the nearest living enemy when placed |
| `position_error_m` | On average over the battle, how far each station really was from where it last said it was. This is a measure of the battle's fog, not of the commander |
| `rounds_fired`, `rounds_per_kill` | Its own guns' rounds, and rounds per enemy killed by any means |
| `own_fire_deaths` | Friendly deaths from the force's own mortar or gun shells. The review page judges each one: the commander's decision, fog, or a harness fault (COMMANDER.md, 15.3) |
| `friendly_fire_deaths` | Friendly deaths at the hands of his own side, by any weapon: the shells above, an aircraft's guns and rockets, or another squad |
| `threat_reported_s` | When a station first listed an enemy weapon or vehicle (as T1, T2...) |
| `silenced`, `silence_noticed_s` | The post a scenario silenced, and how long until the commander ordered or asked it anything. Empty means it never did |
| `output_tokens` | Tokens the model wrote, from the transcript |

### What to look at in each scenario

The outcome first, then:

| Scenario | The numbers that matter | On the review page |
|---|---|---|
| `llm_hidden_gun` | `friendly_lost`, and `threat_reported_s` against the first friendly death | Did a station have eyes on the gun before the main force moved? Did the mortar or a flank deal with it? |
| `llm_two_roads` | `outcome` (10 men there), `friendly_lost`, `duration_s` | Which track it took, and whether it scouted it first. On the no-ambush seeds, slowness is the cost of caution |
| `llm_decoy` | `friendly_lost`, `duration_s` | Whether the main force chased the patrol, or held it and found the garrison |
| `llm_silence` | `silence_noticed_s` | What it did about the silent post: asked it, sent someone, or carried on. Speaking to the post is the only thing the measure counts |
| `llm_guns_only` | `rounds_fired`, `rounds_per_kill` (12 HE in all) | Whether it adjusted from Eyes' corrections, one round at a time, before firing for effect |
| `llm_danger_close` | `friendly_fire_deaths`, `friendly_lost` | Where Bravo was when it called the aircraft in, and how close to the grid |

## 6. What the numbers can and can't tell you

- **A seed fixes the situation, not the battle.** The game's AI, its aim and its paths differ every run. Two battles on one seed by one model can end differently. Compare models over all their seeds, and run a seed twice when one result looks out of line.
- **Winning isn't the whole measure.** A loss to fog is a fair loss: a commander can play well and lose, or badly and win. The scorecard says what happened; the review page says why.
- **Some numbers are about the harness, not the commander.** `position_error_m` is how stale the reports were. `first_contact_s` mostly depends on where the enemy was placed.
- **The silence measure is narrow.** It counts only an order or question to the silent post. A commander that sends Reserve to look without ever calling the post shows as "never" here, so read its turns.
- **Scripted battles are in the records too.** The live tests leave battles with the model "Scripted". Leave them out.
- **Known engine limits that affect outcomes:**
  - The CAS pilot attacks only what he finds himself, with a search modelled on Antistasi's. A prone enemy in grass can take a while.
  - AI pilots bend around high ground on a run-in, which matters to unguided bombs. Air strikes aren't in these six scenarios.
  - Men won't go to building positions over 10 m up, so a garrison holds only what soldiers can reach.
