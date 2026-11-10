# Arma 3 harness: agent cheat sheet

You control a running Arma 3 game through the `arma_*` MCP tools. This page is everything you need. Follow it literally. It works the same in any agent (Claude Code, Codex, OpenCode, Gemini CLI, Cursor, VS Code...); the MCP tool `arma_guide` returns this page too.

**No MCP tools?** Every tool is also a shell command: `host\.venv\Scripts\arma-harness.exe <command>` (from the repo root), printing JSON. `arma_status` -> `status`, `arma_exec(code, target)` -> `exec "<sqf>" --target server`, `arma_listen(since, timeout_s)` -> `listen --since N --timeout 25`, `arma_say(text)` -> `say "<text>"`, `arma_view` -> `view`, `arma_snapshot` -> `snapshot` (prints the PNG path; open it to look). Run `arma-harness.exe --help` for the rest.

## Golden rules

1. **Look before you act.** Call `arma_status` first. If `running` is false, nothing is connected: ask the user to attach (or start a mission). Do not guess.
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

## The chat loop (when the user talks to you from the game)

```
1. arma_listen()                       -> {found, message:{text, name}, kills:[...], next}
2. understand the request (look if needed: arma_snapshot, arma_view)
3. do it with arma_exec on "server"
4. check the result
5. arma_say("short reply")
6. arma_listen(since=<next from step 1>)   <- ALWAYS pass `next` back
```

- **Your name.** Players address you by starting a chat message with your name: `zeus, ...`, `@zeus ...` or `hey zeus ...` (any case). The default is `Claude`. When the user says something like "listen as Zeus", call `arma_set_name("Zeus")` first. After that `arma_listen` and `arma_say` use the name by themselves: your replies show as "Zeus: ..." in your own colour.
  - Several sessions (other agents, other windows) can listen at once, each under its own name. A message reaches only the session it names. `everyone, ...` reaches all of them, so answer it too, briefly.
  - If `arma_set_name` says the name is taken, another live session is using it: tell the user and ask for another name. Use `force=true` only if the user says that session is gone.
  - Names are one word, starting with a letter. `everyone` is reserved.
- **There is no background listener.** You are listening only while an `arma_listen` call is running. When it returns, you are deaf until you call it again. So after every reply, call it again: never end your turn while the user expects you to keep listening.
- `arma_listen` **blocks you** for up to `timeout_s` seconds (default 25, max 300): you can't do or say anything until it returns. `found: false` means the time ran out with no message: call it again with `since` = the `next` it returned. It does **not** prove that anything works.
- **Keep `timeout_s` below your client's tool timeout**, or the client kills the call and you see an error instead of a result (Codex: 60 s by default). The default 25 is safe everywhere. If a listen call errors with a timeout, retry with a smaller `timeout_s`, not a larger one.
- `arma_listen(timeout_s=0)` only checks for waiting messages and returns at once. Use it when the user is also talking to you in the terminal.
- Nothing is lost between calls: the game keeps capturing chat while you are busy, and the next call with `since` picks it up.
- Before starting a listen loop, tell the user in one line: "Listening for in-game chat; stop me when you want me back."
- **"Is the listener on?"** Call `arma_status` and read `listener`; never answer from an `arma_listen` result:
  - `chat_observer_installed: {"2": true}`: the game is capturing chat (installed automatically at attach and on every mission start). `false` or missing: say so, and call `arma_listen` (it installs it).
  - `sessions`: one entry per name that has listened. Find **your** name.
    - `listen_call_waiting_now`: true only while a listen call is running. If false, say plainly "I'm not listening right now; I will start", then call `arma_listen`.
    - `messages_since_last_listen_started`: messages to you that may be unread. If you see any, handle them (call `arma_listen` with `since` = `last_listen_since`).
    - `session_alive: false` is a session that has ended (its name is free).
  - Report these facts as they are. Do not add "working" or "OK" on top.
- `kills` lists deaths since the last call (`victim`, `killer`, `weapon`, `distance`). Use it for "what happened?".
- If a tool returns `bridge unreachable`, the game was closed or detached. Stop and tell the user.

## Seeing

- `arma_snapshot()` returns an image of exactly what the player sees. Use it for "what do you see", "this guy", "that house".
- `arma_view(radius=300)` lists on-screen objects: `name`, `pos` (world [x,y,z]), `distance`, `screen` [x,y] (0..1, 0.5 = centre), `seen` (1 = clear line of sight). Match the image to this list using `screen` x/y to get world positions.
- "This guy" = the unit nearest the centre of the screen. Recipe below.
- `arma_snapshot(camera_pos=[x,y,z], camera_target=[x,y,z], hide_hud=true)` looks from anywhere (z is ATL), then restores the view. Use it to check your own work: from above (~90 m up, 30 m to the side) for layout, at eye level (z 1.8) for heights and facing. It works even while the player is in Zeus or Splendid Camera.

## Recipes (tested; copy and adjust)

All run with `target: "server"`.

**Player position and facing**
```sqf
private _p = allPlayers # 0; [getPosATL _p, getDir _p, mapGridPosition _p]
```

**Spawn a vehicle next to the player**
```sqf
private _p = allPlayers # 0;
private _pos = (_p getPos [15, getDir _p + 40]) findEmptyPosition [0, 50, "B_MRAP_01_hmg_F"];
private _v = createVehicle ["B_MRAP_01_hmg_F", _pos, [], 0, "NONE"];
_v setDir getDir _p; [getText (configOf _v >> "displayName"), round (_p distance _v)]
```
Classes: `B_MRAP_01_hmg_F` (Hunter HMG), `B_APC_Wheeled_01_cannon_F` (Badger IFV), `B_MBT_01_cannon_F` (tank), `B_Heli_Transport_01_F` (Ghost Hawk, spawn with `"FLY"` instead of `"NONE"`), `C_Offroad_01_F` (civilian car).

**Spawn an enemy squad at a place**
```sqf
private _at = [13993, 18709, 0];
private _grp = [_at, east, (configFile >> "CfgGroups" >> "East" >> "OPF_F" >> "Infantry" >> "OIA_InfSquad")] call BIS_fnc_spawnGroup;
[_grp, _at, 100] call BIS_fnc_taskPatrol;
missionNamespace setVariable ["agent_enemy", _grp];
count units _grp
```

**Put units inside buildings** (after spawning `_grp`)
```sqf
private _houses = (nearestObjects [_at, ["House"], 120]) select {count (_x buildingPos -1) > 3};
{ _x setPosATL (selectRandom ((selectRandom _houses) buildingPos -1)); _x disableAI "PATH" } forEach units _grp;
```

**Create a task that completes when they are all dead**
```sqf
private _grp = missionNamespace getVariable "agent_enemy";
[west, "agentTask1", ["Eliminate the enemy.", "Clear the area", ""], getPosATL leader _grp, "ASSIGNED", 1, true, "attack"] call BIS_fnc_taskCreate;
[_grp] spawn { params ["_g"]; waitUntil { sleep 2; ({alive _x} count units _g) == 0 }; ["agentTask1", "SUCCEEDED"] call BIS_fnc_taskSetState };
true
```
Use a new task id (`agentTask2`, ...) each time.

**Night, fog, weather**
```sqf
[[2035, 6, 10, 23, 30]] remoteExec ["setDate"];   // full moon: night stays visible
0 setOvercast 0.3; 0 setFog [0.2, 0.01, 40]; forceWeatherChange; true
```
Daytime: same with hour 12. Most other dates at night are pitch black: keep 2035-06-10.

**Give the squad night vision**
```sqf
{ if (hmd _x == "") then { _x linkItem "NVGoggles" } } forEach units group (allPlayers # 0); true
```

**Change the squad's weapons**
```sqf
private _swap = { params ["_u", "_w", "_mag", "_n"];
  { _u removeMagazines _x } forEach (getArray (configFile >> "CfgWeapons" >> primaryWeapon _u >> "magazines"));
  _u removeWeapon primaryWeapon _u;
  for "_i" from 1 to _n do { _u addMagazine _mag };
  _u addWeapon _w; _u selectWeapon _w; [name _u, primaryWeapon _u] };
(units group (allPlayers # 0)) apply { [_x, "arifle_AKM_F", "30Rnd_762x39_Mag_F", 6] call _swap }
```
Weapons: `arifle_AKM_F` + `30Rnd_762x39_Mag_F`; `LMG_Zafir_F` + `150Rnd_762x54_Box`; `arifle_MX_F` + `30Rnd_65x39_caseless_mag`; `srifle_LRR_F` + `7Rnd_408_Mag`. **Before using any class, check it exists:** `isClass (configFile >> "CfgWeapons" >> "NAME")` (vehicles: `CfgVehicles`). If false, pick another and tell the user.

**Find a weapon or vehicle by name**
```sqf
("toLowerANSI getText (_x >> 'displayName') find 'rpk' >= 0 and {getNumber (_x >> 'scope') == 2}" configClasses (configFile >> "CfgWeapons")) apply {configName _x}
```

**"This guy" (unit in front of the player)**: target `interface`
```sqf
private _dir = (positionCameraToWorld [0,0,0]) vectorFromTo (positionCameraToWorld [0,0,100]);
private _c = ((player nearEntities ["CAManBase", 80]) - [player]) apply {
  private _r = (getPosATL _x) vectorDiff (getPosATL player);
  [(_r vectorDotProduct _dir) / ((vectorMagnitude _r) max 0.1), _x] } select {(_x # 0) > 0.8};
_c sort false; if (_c isEqualTo []) then {"nobody"} else {[name ((_c # 0) # 1), typeOf ((_c # 0) # 1)]}
```

**Spawn an animal or civilian**
```sqf
private _p = allPlayers # 0; createAgent ["Goat_random_F", _p getPos [2, getDir _p], [], 0, "CAN_COLLIDE"]; true
```
Animals: `Goat_random_F`, `Sheep_random_F`, `Fin_random_F` (dog), `Hen_random_F`.

**Marker arrow above something**
```sqf
private _a = createVehicle ["Sign_Arrow_Large_Blue_F", [0,0,0], [], 0, "CAN_COLLIDE"];
_a setPosATL ((getPosATL TARGET) vectorAdd [0,0,4]); true
```

**Bombardment (with safety check)**: never hit within 250 m of the player's squad
```sqf
private _at = [13993, 18709, 0];
private _near = selectMin ((units group (allPlayers # 0)) apply {_x distance2D _at});
if (_near < 250) exitWith {["too close", round _near]};
[_at] spawn { params ["_at"]; for "_i" from 1 to 30 do {
  private _s = createVehicle ["Sh_155mm_AMOS", (_at getPos [random 120, random 360]) vectorAdd [0,0,150], [], 0, "CAN_COLLIDE"];
  _s setVelocity [0,0,-150]; sleep 0.4 } };
["firing", round _near]
```
If "too close", tell the user and do not fire.

## Building with objects (outposts, camps, clutter)

Learned the hard way. Follow these steps in order.

1. **Check the world first.** `worldName` can change mid-session (a mission restart raises the bridge `epoch`). VR ground is at 5 m ASL, not 0.
2. **Pick a clear, flat site that is not where the player stands.** Offset it 30-60 m from the squad, then check it: `nearestObjects [_c, [], 45]` (skip `CAManBase`) should be empty, and `getTerrainHeightASL` at the centre and corners should match.
3. **Check classes and measure them** before laying anything out:
   `_t = _cls createVehicleLocal [0,0,0]; _b = boundingBoxReal _t; deleteVehicle _t; (_b # 1) vectorDiff (_b # 0)` -> `[length, width, height]`. The long side is the model's x axis: at `dir 0` it runs east-west, at `dir 90` north-south. Lay walls end to end using the measured length.
4. **Place with the recipe below.** `createSimpleObject` takes a **world position (ASL of the model centre)**, not ATL. Passing `[x, y, 0]` buries everything. Do not compute the offset yourself: put a temporary real object where you want it, copy its world position and orientation, then delete it. The same recipe puts small items on furniture: use `z` = the table top (camping table 0.8, workbench 0.95).
5. **Get model paths from config** (`getText (configOf _t >> "model")`). `fileExists` returns false for `.p3d` files even when they exist, so do not use it.
6. **Keep handles** in `missionNamespace` (`agent_outpost`, ...) so you can fix or delete things later. `deleteVehicle` works on simple objects (`allSimpleObjects` updates on the next frame; its `empty.p3d` entries at -1000,-1000 are the engine's, so leave them alone).
7. **Look at it** with `arma_snapshot(camera_pos=...)` from above and from eye level, and fix what you see (for example, a sign showing its back: `_x setVectorDirAndUp [(vectorDir _x) vectorMultiply -1, vectorUp _x]`).
8. **Simple objects are dead props**: no simulation, no building positions, a campfire cannot burn and a flag does not show its cloth. Use real objects (`createVehicle`) for anything that must work: `Land_Campfire_F` + `_f inflame true`, flags, vehicles.

**Place simple objects from a layout** (offsets relative to a centre; `[class, [dx, dy, z], dir]`)
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
- **Set one up:** `arma-harness.exe commander start <scenario> [--seed N]`. It prints the command that launches the commander's own locked-down Claude Code session. Don't play the commander from your own session.
- **Never help the commander.** Don't use the `arma_*` tools to tell it anything about the battle, or to change the battle while it runs. That breaks the fog of war, and with it what the battle measures. Golden rule 3 applies too: ask before starting a game.
- **Afterwards:** `commander review` writes a replay page of the battle, and `commander compare <scenario> [--csv]` puts battles side by side.
- **Docs:** running and scoring battles with real LLMs is in `docs/COMMANDER_BENCHMARK.md`; the design is in `docs/COMMANDER.md`, and the formal model in `docs/COMMANDER_MODEL.md`. The game side is `host/src/arma_harness/adapters/commander/`, one SQF file per function, linted with `tools/lint_commander.py`.

## When stuck

1. `arma_errors()` for recent script errors.
2. `arma_status()` to see if the game is still connected.
3. Tell the user plainly what failed and what you tried. Do not invent success.
