# Arma 3 harness: agent cheat sheet

You control a running Arma 3 game through the `arma_*` MCP tools. This page is everything you need. Follow it literally. It works the same in any agent (Claude Code, Codex, OpenCode, Gemini CLI, Cursor, VS Code...); the MCP tool `arma_guide` returns this page too.

**No MCP tools?** Every tool is also a shell command: `host\.venv\Scripts\arma-harness.exe <command>` (from the repo root), printing JSON. `arma_status` -> `status`, `arma_exec(code, target)` -> `exec "<sqf>" --target server`, `arma_listen(since, timeout_s)` -> `listen --since N --timeout 25`, `arma_say(text)` -> `say "<text>"`, `arma_view` -> `view`, `arma_snapshot` -> `snapshot` (prints the PNG path; open it to look), `arma_commands(query)` -> `commands <words>`, `arma_run(name, args)` -> `run <name> '<json args>'`. Run `arma-harness.exe --help` for the rest.

## Golden rules

1. **Look before you act.** Call `arma_status` first. If `running` is false, the harness isn't connected to a game, which says nothing about whether the user's game is open. If the user is playing (or asks you to attach), call `arma_attach` yourself: it finds their game. If it answers "no bridge", the game isn't in a mission as host with `@Pythia` and `@brmh` loaded: tell the user that. If the user isn't playing, ask whether to attach or to start a mission. Do not guess.
2. **Never delete files** in `%LOCALAPPDATA%\arma-harness\` (`server_root\` holds links into the Arma install). Never run `arma_stop` while the user is playing in an attached game unless they ask; in attached mode it only detaches, but it ends your session.
3. **Do not start games** (`arma_start`, `arma_client_start`) while the user is playing. Ask first.
4. **Check every result.** A tool result has `ok`. If `ok` is false, read `error` and each `results[i].errors[*].text`, fix the code, and retry once. Never tell the user something worked without `ok: true`.
5. **Keep SQF small.** One job per `arma_exec`. Return a value you can check, e.g. `[count units _grp, getPosATL _v]`.
6. **Reply in game with `arma_say`**, one or two short sentences. Say what you actually did, with numbers (distance, count, names).

## Where code runs (the most common mistake)

| Target | Use for |
|---|---|
| `server` | Spawning units/vehicles/objects, weather, time, tasks, AI orders. **Default.** |
| `interface` | Things about the player's own screen/camera: `player`, `positionCameraToWorld`, `hint`. |
| `all` | Rarely. |

- On `server` in a **dedicated** server, `player` is **null**. Use `allPlayers # 0` for "the player", or `allPlayers select {name _x == "<player name>"}`.
- In a **hosted** game (the usual attached case) server and interface are the same machine; `allPlayers # 0` still works, so always use it on the server.

## Talking with the user in game

Players address you by starting a chat message with your name: `zeus, ...`, `@zeus ...` or `hey zeus ...` (any case). The default is `Claude`. When the user says something like "listen as Zeus", call `arma_set_name("Zeus")` first. After that your replies (`arma_say`) show as "Zeus: ..." in your own colour.

- Several sessions (other agents, other windows) can listen at once, each under its own name. A message reaches only the session it names. `everyone, ...` reaches all of them, so answer it too, briefly.
- If `arma_set_name` says the name is taken, another live session is using it: tell the user and ask for another name. Use `force=true` only if the user says that session is gone.
- Names are one word, starting with a letter. `everyone` is reserved.

### Chat wakes (Claude Code and OpenCode): use these first

```
1. arma_set_name("Zeus")              (if the user named you)
2. arma_chat_wake()                   -> ok: true, via ...; a test wake follows
3. end your turn
   ... a player types "zeus, ..." -> your next turn starts with it, as a <channel source="arma"> block
4. understand it, do it (arma_exec on "server"), check the result
5. arma_say("short reply"), then end your turn
```

- Each message to you **starts your turn** by itself, even long after the last one. Nothing runs or costs anything while it's quiet. **Don't call `arma_listen`** while wakes are on.
- **The test wake.** Right after `arma_chat_wake`, a test message reaches you as a wake of its own. When it does, tell the user in one line that chat wakes work (not in game), and end your turn. If it never arrives, wakes don't work in this session: call `arma_chat_wake(on=false)` and use the listen loop below. In Claude Code they work only when it was launched with `--dangerously-load-development-channels server:arma`.
- If `arma_chat_wake` answers `ok: false` (another client, or OpenCode's server unreachable), use the listen loop below.
- A wake lists the deaths since the last message, under "Deaths since the last message". Use it for "what happened?".
- Wakes keep working when the game is closed and attached again, and after a mission restart.

### The listen loop (any other client)

```
1. arma_listen()                       -> {found, message:{text, name}, kills:[...], next}
2. understand the request (look if needed: arma_snapshot, arma_view)
3. do it with arma_exec on "server"
4. check the result
5. arma_say("short reply")
6. arma_listen(since=<next from step 1>)   <- ALWAYS pass `next` back
```

- **You hear chat only while a listen call runs.** When it returns, you are deaf until you call it again. So after every reply, call it again: never end your turn while the user expects you to keep listening.
- `arma_listen` **blocks you** for up to `timeout_s` seconds (default 25, max 300): you can't do or say anything until it returns. `found: false` means the time ran out with no message: call it again with `since` = the `next` it returned. It does **not** prove that anything works.
- **Keep `timeout_s` below your client's tool timeout**, or the client kills the call and you see an error instead of a result (Codex: 60 s by default). The default 25 is safe everywhere. If a listen call errors with a timeout, retry with a smaller `timeout_s`, not a larger one.
- `arma_listen(timeout_s=0)` only checks for waiting messages and returns at once. Use it when the user is also talking to you in the terminal.
- Nothing is lost between calls: the game keeps capturing chat while you are busy, and the next call with `since` picks it up.
- Before starting a listen loop, tell the user in one line: "Listening for in-game chat; stop me when you want me back."
- `kills` lists deaths since the last call (`victim`, `killer`, `weapon`, `distance`). Use it for "what happened?".

### "Is the listener on?"

Call `arma_status` and read `listener`; never answer from an `arma_listen` result or from memory:

- `chat_observer_installed: {"2": true}`: the game is capturing chat (installed automatically at attach and on every mission start). `false` or missing: say so, and call `arma_listen` (it installs it).
- `sessions`: one entry per name that has listened. Find **your** name.
  - `chat_wake`: how messages to you start your turn (`claude code channel` or `opencode session ...`), or `off`.
  - `listen_call_waiting_now`: true while something is waiting on chat for you: your listen call, or the wake. If it's false and `chat_wake` is `off`, say plainly "I'm not listening right now; I will start", then start.
  - `messages_since_last_listen_started`: messages to you that may be unread. If you see any, handle them.
  - `session_alive: false` is a session that has ended (its name is free).
- Report these facts as they are. Do not add "working" or "OK" on top.

If a tool returns `bridge unreachable`, the game was closed or detached. Tell the user.

## Seeing

- `arma_snapshot()` returns an image of exactly what the player sees. Use it for "what do you see", "this guy", "that house".
- `arma_view(radius=300)` lists on-screen objects: `name`, `pos` (world [x,y,z]), `distance`, `screen` [x,y] (0..1, 0.5 = centre), `seen` (1 = clear line of sight). Match the image to this list using `screen` x/y to get world positions.
- "This guy" = the unit nearest the centre of the screen: `arma_run("unit_in_view")`.
- `arma_snapshot(camera_pos=[x,y,z], camera_target=[x,y,z], hide_hud=true)` looks from anywhere (z is ATL), then restores the view. Use it to check your own work: from above (~90 m up, 30 m to the side) for layout, at eye level (z 1.8) for heights and facing. It works even while the player is in Zeus or Splendid Camera.

## The command library (try it before writing SQF)

Tested commands for common jobs, run by name with checked arguments. They're faster and safer than SQF you write
on the spot: each checks its classes and references and says plainly what's wrong.

- **Find one:** `arma_commands("spawn car")` returns the best matches, each with what it does, its parameters
  (types, defaults), what it returns and an example. `arma_commands()` with no words is the whole index.
- **Run it:** `arma_run("spawn_vehicle", {"class": "C_Offroad_01_F"})`. Arguments go by name; anything left out
  takes its default. It runs on the right machine by itself. The answer is `{ok: true, result}` or
  `{ok: false, error}` saying what to fix: fix it and run again, don't fall back to SQF for the same job.
- **References you can pass:** `"player"`, a player's or unit's name, a net id from `arma_exec`, a grid such as
  `"034 030"` for a place, or a `"made:N"` handle.
- **Handles:** anything a command creates comes back with a `"made:N"` handle. `list_made` shows them, and
  `delete_made("made:N")` (or `"all"`) removes it, crews and men included. Use it for "undo that" or "clear it up".
- **Nothing fits?** Write SQF with `arma_exec` as below. If it's a job players will ask for again, tell the user it
  could become a library command (one file in `host/src/arma_harness/library/<area>/`).

The index:

| Area | Commands |
|---|---|
| player | `player_info` (where someone is: grid, position, facing, vehicle, squad) |
| spawn | `spawn_vehicle`, `spawn_group` (an infantry group of a side, patrolling), `spawn_animal` |
| units | `garrison` (men into the buildings around a place), `squad_weapons`, `squad_nvg`, `heal`, `teleport` |
| world | `set_time_weather` (time, overcast, fog, rain; night with a full moon) |
| tasks | `task_eliminate` (a task that completes when a group is dead) |
| fire | `bombard` (an artillery barrage, refused within the safety distance of any player's side) |
| find | `find_class` (classes by display name), `unit_in_view` ("this guy": who the player's looking at) |
| markers | `arrow_above` (an arrow over something, to show the player) |
| build | `measure_class`, `place_layout` (props from a layout around a centre) |
| cleanup | `list_made`, `delete_made` |

Common asks: "spawn me a car" is `spawn_vehicle`; "put enemies in that village" is `spawn_group`, then
`garrison` and `task_eliminate`; "make it night" is `set_time_weather` with `hour` 23; "who's that?" is
`unit_in_view`; "get rid of it" is `delete_made`.

## Building with objects (outposts, camps, clutter)

Learned the hard way. Follow these steps in order.

1. **Check the world first.** `worldName` can change mid-session (a mission restart raises the bridge `epoch`). VR ground is at 5 m ASL, not 0.
2. **Pick a clear, flat site that is not where the player stands.** Offset it 30-60 m from the squad, then check it: `nearestObjects [_c, [], 45]` (skip `CAManBase`) should be empty, and `getTerrainHeightASL` at the centre and corners should match.
3. **Check classes and measure them** before laying anything out: `arma_run("measure_class", {"class": ...})` -> `[length, width, height]`. The long side is the model's x axis: at `dir 0` it runs east-west, at `dir 90` north-south. Lay walls end to end using the measured length.
4. **Place with `place_layout`** (`arma_commands("place_layout")`), or the SQF below when you need more control. `createSimpleObject` takes a **world position (ASL of the model centre)**, not ATL. Passing `[x, y, 0]` buries everything. Do not compute the offset yourself: put a temporary real object where you want it, copy its world position and orientation, then delete it. The same recipe puts small items on furniture: use `z` = the table top (camping table 0.8, workbench 0.95).
5. **Get model paths from config** (`getText (configOf _t >> "model")`). `fileExists` returns false for `.p3d` files even when they exist, so do not use it.
6. **Keep handles**: `place_layout` returns a `made:N` handle that `delete_made` removes; with your own SQF, keep them in `missionNamespace` (`agent_outpost`, ...) so you can fix or delete things later. `deleteVehicle` works on simple objects (`allSimpleObjects` updates on the next frame; its `empty.p3d` entries at -1000,-1000 are the engine's, so leave them alone).
7. **Look at it** with `arma_snapshot(camera_pos=...)` from above and from eye level, and fix what you see (for example, a sign showing its back: `_x setVectorDirAndUp [(vectorDir _x) vectorMultiply -1, vectorUp _x]`).
8. **Simple objects are dead props**: no simulation, no building positions, a campfire cannot burn and a flag does not show its cloth. Use real objects (`createVehicle`) for anything that must work: `Land_Campfire_F` + `_f inflame true`, flags, vehicles.

**Place simple objects from a layout** by hand, as `place_layout` does (offsets relative to a centre; `[class, [dx, dy, z], dir]`)
```sqf
private _c = [4040, 4060];
private _L = [["Land_HBarrier_Big_F", [-22.5, 18, 0], 0], ["Land_Cargo_HQ_V1_F", [-12, 6, 0], 180], ["Land_CampingTable_F", [2.5, 7, 0], 0], ["Land_Laptop_unfolded_F", [2, 7, 0.8], 180]];
private _made = [];
{ _x params ["_cls", "_o", "_d"];
  private _t = _cls createVehicleLocal [0,0,0]; _t enableSimulation false; _t setDir _d;
  _t setPosATL [(_c # 0) + (_o # 0), (_c # 1) + (_o # 1), _o # 2];
  private _pw = getPosWorld _t; private _vd = vectorDir _t; private _vu = vectorUp _t;
  private _m = getText (configOf _t >> "model"); deleteVehicle _t;
  private _s = createSimpleObject [_m, _pw]; _s setVectorDirAndUp [_vd, _vu]; _made pushBack _s } forEach _L;
missionNamespace setVariable ["agent_outpost", _made];
[count _L, {isNull _x} count _made]
```
Measured sizes (L x W x H, m): `Land_HBarrier_Big_F` 9 x 2.6 x 2.6, `Land_HBarrier_5_F` 5.8 x 1.7 x 1.6, `Land_Cargo_HQ_V1_F` 17.8 x 13.5, `Land_Cargo_Patrol_V1_F` 6.7 x 6.8, `Land_Cargo_House_V1_F` 6.2 x 8.9, `CamoNet_BLUFOR_open_F` 21.6 x 11.8, `Land_Razorwire_F` 8.5, `Land_Cargo20_military_green_F` 9.4 x 2.5, `Land_ClothesLine_01_F` 10.3.

**What makes a place feel lived in**: separate zones, each with its own clutter, and a few people.
- Mess area: `Land_Campfire_F` (real, lit), `Land_Bench_F` around it, `Land_CampingTable_F` + `Land_CampingChair_V1_F`/`V2_F`, with `Land_BakedBeans_F`, `Land_Can_V3_F`, `Land_Canteen_F`, `Land_Map_altis_F`, `Land_Camping_Light_F` on the table.
- Sleeping: `Land_TentDome_F`, `Land_TentA_F`, `Land_Ground_sheet_blue_F` + `Land_Sleeping_bag_F`, `Land_ClothesLine_01_F` along a wall.
- Command: `Land_TTowerSmall_2_F` (radio mast), `Land_SatelliteAntenna_01_F`, a table with `Land_Laptop_unfolded_F`, `Land_PortableLongRangeRadio_F`, `Land_Notepad_F`, `Land_File1_F`.
- Workshop: `Land_Workbench_01_F`, `Land_ToolTrolley_01_F`, `Land_WeldingTrolley_01_F`, `Land_EngineCrane_01_F`, `Land_Tyres_F`, `Land_MetalBarrel_F`, `Land_CanisterFuel_F`.
- Supplies under the camo net: `Box_NATO_Ammo_F`, `Box_NATO_Wps_F`, `Land_Pallet_MilBoxes_F`, `Land_FoodSacks_01_large_brown_F`, `Land_WaterBottle_01_stack_F`.
- Mess: `Land_GarbageBags_F`, `Land_GarbagePallet_F`, `Land_BarrelTrash_F`, `Land_Garbage_square5_F` (ground litter decal).
- Gate: leave a 6 m gap, with `Land_BagFence_Round_F` on each side, a `Land_CncBarrier_stripes_F` chicane, and `Land_Sign_WarningMilitaryArea_F` facing outward.
- People: `_g = createGroup [west, true]; _u = _g createUnit [...]; _u setDir ...; [_u, "SIT_LOW", "ASIS"] call BIS_fnc_ambientAnim`. Animation sets that look right: `SIT_LOW` (on the ground at the fire), `WATCH` (gate guard), `BRIEFING` (at a table), `REPAIR_VEH_STAND` (at the workbench).

## SQF traps

- No `//` comments are needed; they are allowed but keep code short.
- Strings use double quotes; inside `arma_exec` JSON you may use single quotes for SQF strings: `'text'`.
- `#` is array index: `_arr # 0`. Positions are `[x, y, z]`; `z` is height.
- `sleep` and `waitUntil` only work inside `spawn { }` (or with `scheduled: true`).
- An error inside a loop is reported once with `repeats: N`. Fix the first error first.
- Unknown command or wrong syntax? Use the a3ref tools (`search`, `get`, `lint_sqf`) if you have them.

## Commander mode (an LLM commands squads by radio)

A separate mode where an LLM commands AI squads in a battle it can't see, only through radio-like `commander_*` tools, under fog of war. If you're asked to run or review a commander battle, you are its **operator**, not its commander.

- **List the scenarios:** `arma-harness.exe commander list`. The `llm_*` ones are the benchmark, with their seeds.
- **Set one up:** `arma-harness.exe commander start <scenario> [--seed N]`. It prints the command that launches the commander's own locked-down Claude Code session.
- **Any other model, through OpenCode:** follow `docs/COMMANDER_OPENCODE.md`. In short: `arma-harness.exe commander doctor --client opencode` checks everything and lists the models, then `commander start <scenario> --client opencode --model <provider/model>` boots the battle and starts the commander's session itself. Ask the user which model. Don't play the commander from your own session.
- **Never help the commander.** Don't use the `arma_*` tools to tell it anything about the battle, or to change the battle while it runs. That breaks the fog of war, and with it what the battle measures. Golden rule 3 applies too: ask before starting a game.
- **Afterwards:** `commander review` writes a replay page of the battle, and `commander compare <scenario> [--csv]` puts battles side by side.
- **Docs:** running and scoring battles with real LLMs is in `docs/COMMANDER_BENCHMARK.md`, and running them in OpenCode in `docs/COMMANDER_OPENCODE.md`; the design is in `docs/COMMANDER.md`, and the formal model in `docs/COMMANDER_MODEL.md`. The game side is `host/src/arma_harness/adapters/commander/`, one SQF file per function, linted with `tools/lint_commander.py`.

## When stuck

1. `arma_errors()` for recent script errors.
2. `arma_status()` to see if the game is still connected.
3. Tell the user plainly what failed and what you tried. Do not invent success.
