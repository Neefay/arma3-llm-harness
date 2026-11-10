# arma-harness

Drive and observe Arma 3 from LLM agents and scripts. The harness is a standard MCP server, so it works with any MCP-capable agent (Claude Code, Codex, OpenCode, Gemini CLI, Cursor, VS Code, ...), and everything is also a command-line tool that prints JSON. With it you can:
- boot missions on an isolated local dedicated server, with headless clients and a rendering client, or attach to a game you're playing;
- run SQF on any machine, with script errors attributed to the request that caused them;
- stream structured events;
- take in-engine screenshots (GUI included) and terrain maps;
- talk to the agent from in-game chat and have it act on the world ([demo](docs/DEMO.md));
- hot-reload mission code;
- run declarative test scenarios;
- let an LLM command AI squads by radio, under fog of war, and score how it does ([commander mode](#commander-mode)).

Agents get their instructions from [`AGENTS.md`](AGENTS.md): rules, where code runs, the chat loop and tested recipes.

**Dev only.** Everything binds to 127.0.0.1, the server runs in LAN mode without BattlEye, and the in-game probe stays inert unless the harness wrote a session file for that exact game process.

```
any MCP agent ──MCP stdio──▶ arma-harness-mcp (host/, Python 3.11+)
scripts / CLI ─────────────▶ arma-harness (same operations, JSON out)
                             │ HTTP 127.0.0.1:<ephemeral> + per-run token
                             ▼
  arma3server_x64.exe  ◀── @brmh mod: Pythia bridge (python/) + SQF probe (addons/main) + brmh_x64.dll (brmh_ext/)
   hub: routes requests to machines over CBA events, gathers results and events
     ├── headless clients (arma3server_x64 -client)
     └── rendering client (arma3_x64): in-engine frame capture via the Rust extension
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how it works and the engine facts it relies on.

---

## Quick start (first time)

About 15 minutes, most of it downloads and the first build. All commands are PowerShell, run from the repo root.

**1. Install the prerequisites**

| What | How |
|---|---|
| Arma 3 (Steam), with the Workshop mods **CBA_A3** and **Pythia** | Subscribe in the Workshop, then start the game once so Steam downloads them |
| Python 3.11+ | [python.org](https://www.python.org/downloads/) (tick "Add to PATH") |
| Rust | [rustup.rs](https://rustup.rs), then `rustup update stable` |
| HEMTT 1.23+ | `winget install BrettMayson.HEMTT`, or download it from [hemtt.dev](https://hemtt.dev) |
| An MCP-capable agent (optional, for the LLM side): Claude Code, Codex, OpenCode, Gemini CLI, Cursor, VS Code | see [Use from an agent](#use-from-an-agent) |

**2. Build**

```powershell
git clone https://github.com/Neefay/arma3-llm-harness.git arma-harness
cd arma-harness
python -m venv host\.venv
host\.venv\Scripts\python -m pip install -e ".\host[dev]"
host\.venv\Scripts\python tools\build.py --check
```

The last line builds the mod into `%LOCALAPPDATA%\arma-harness\mods\@brmh` and runs every offline test. It should end with all tests passing and `deployed ...`.

**3. Check it against the real game.** This boots a local dedicated server with the bundled self-test mission (no game window) and should print `"verdict": "pass"` within about a minute:

```powershell
host\.venv\Scripts\arma-harness.exe scenario selftest
```

**4. Connect your agent.** Run `host\.venv\Scripts\arma-harness.exe setup-agents`. It writes the project MCP config for Claude Code, Codex, OpenCode, Gemini CLI, Cursor and VS Code, pointing at this clone, and never overwrites a file you already have. Then start your agent in this folder (`claude`, `codex`, `opencode`, `gemini`, ...). It now has the `arma_*` tools, and reads [`AGENTS.md`](AGENTS.md), the agent cheat sheet. Try: *"Start the selftest mission with a client and take a snapshot."*

**5. Use it in your own game (optional).**
1. In the Arma 3 Launcher, add the local mod `%LOCALAPPDATA%\arma-harness\mods\@brmh` (Mods → ⋯ → Add local mod), enable it with CBA_A3 and Pythia, and **turn BattlEye off**.
2. Start a mission as host: an Eden preview, singleplayer, or Play → Multiplayer → host.
3. Once you are in the mission, run `host\.venv\Scripts\arma-harness.exe attach`, then `arma-harness scenario attached_check` to certify it.

To talk to your agent from in-game chat, see the demo: [`docs/DEMO.md`](docs/DEMO.md).

### If something goes wrong

| Symptom | Fix |
|---|---|
| `build.py` says NOT DEPLOYED | A running game has the mod loaded (its files are locked). Quit Arma and run it again. |
| `attach`: "no bridge" | You must be *in* a mission (not the main menu), as host, with `@Pythia` and `@brmh` enabled. Check the RPT for `@Pythia mod and extension loaded`. |
| `attach` finds several Arma processes | Pass `--pid <pid>` of the one you're playing. |
| Snapshot is black | The game window is minimised, or a loading screen is showing. Restore the window and retry. |
| Anything else | `arma-harness status`, then `arma-harness rpt --machine server --tail 50`, and the logs in `%LOCALAPPDATA%\arma-harness\logs\`. |

---

## Requirements

- **Windows 10/11** and **Arma 3 2.22+** (Steam), with these Workshop mods: **CBA_A3**, **Pythia**, plus whatever your mission needs (rounds_framework needs **ace**).
- **To build:**
  - Rust ≥ 1.90 (`rustup update stable`);
  - Python ≥ 3.11;
  - [HEMTT](https://hemtt.dev) 1.23+: `tools/build.py` uses `$HEMTT`, then `hemtt` on `PATH`, then `%LOCALAPPDATA%\arma-harness\tools\hemtt-*\hemtt.exe`.

## Install and build

```powershell
cd host
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
cd ..
host\.venv\Scripts\python tools\build.py --check   # cargo + hemtt -> %LOCALAPPDATA%\arma-harness\mods\@brmh, then all offline tests
```

**Runtime folder.** Everything the harness writes at runtime lives in `%LOCALAPPDATA%\arma-harness\` (override with `BRMH_HOME`), never in the repo or the Arma install:

| Folder | Holds |
|---|---|
| `mods\@brmh` | the built mod |
| `server_root\` | the isolated server: a copied server exe, junctions to the install's data folders, its own `MPMissions` |
| `runs\<id>\` | per-run `server.cfg`, profiles (RPTs) and scenario reports |
| `sessions\` | per-process session and port files |
| `captures\` | snapshots and maps |
| `logs\audit.jsonl` | every executed request |
| `logs\brmh_ext.log`, `logs\bridge-<pid>.log` | the Rust extension's log; Python errors inside the game |

> `server_root\` contains **directory junctions into the Arma install**. Never delete it with a tool that follows junctions. Use `rmdir` on each junction, or `arma_harness.serverroot.remove()`.

## Use from an agent

The harness is a standard MCP server (stdio), so any MCP-capable agent can drive it. Two pieces:

1. **The MCP server config.** `arma-harness setup-agents [claude codex opencode gemini cursor vscode]` writes the project-scoped file each client reads, with absolute paths to this clone:

   | Client | File written | Instructions it reads |
   |---|---|---|
   | Claude Code | `.mcp.json` | `CLAUDE.md`, which imports `AGENTS.md` |
   | Codex | `.codex/config.toml` (project must be trusted), with `tool_timeout_sec` raised | `AGENTS.md` natively |
   | Gemini CLI | `.gemini/settings.json`, which also sets `context.fileName` to `AGENTS.md` | `AGENTS.md` |
   | Cursor | `.cursor/mcp.json` | `AGENTS.md` natively |
   | OpenCode | `opencode.json` (current schema: a `local` server under `mcp`, with `timeout` raised) | `AGENTS.md` natively (it ignores `CLAUDE.md` when `AGENTS.md` exists) |
   | VS Code (Copilot agent mode) | `.vscode/mcp.json` | `AGENTS.md` (setting `chat.useAgentsMdFile`) |

   **OpenCode 2** uses a different layout: servers sit under `mcp.servers`, and timeouts are split into `startup`, `catalog` and `execution` (tool calls default to 12 hours, so nothing needs raising). If your OpenCode rejects the generated file, use:

   ```json
   { "$schema": "https://opencode.ai/config.json",
     "mcp": { "servers": { "arma": { "type": "local", "command": ["<repo>/host/.venv/Scripts/arma-harness-mcp.exe"], "cwd": "<repo>" } } } }
   ```

   These files are personal and git-ignored. A file that already exists is left alone unless you pass `--force` (the old one is kept as `.bak`); `--dry-run` shows what would be written. To use the harness from another project, for example your mission repo, register the same command there: `<repo>/host/.venv/Scripts/arma-harness-mcp.exe`.
2. **The agent instructions.** [`AGENTS.md`](AGENTS.md) is the cheat sheet: rules, where code runs, the chat loop and tested recipes. Agents that don't load instruction files can get it from the `arma_guide` tool, or from `arma-harness guide` on the command line. Agents without MCP can use the CLI directly: every tool is a subcommand that prints JSON.

**Tool-call timeouts.** Clients cancel tool calls that run too long (Codex's default is 60 s). `arma_listen` waits 25 s by default for that reason. Chat is captured in game whether or not a call is waiting, so short, repeated calls lose nothing.

The game processes survive MCP server restarts: they are started through WMI, outside the MCP client's job object.

### Tools

| Tool | What it does |
|---|---|
| `arma_guide` | The agent cheat sheet ([`AGENTS.md`](AGENTS.md)), for clients that don't load instruction files |
| `arma_status` | Run state, processes, bridge health, connected machines, and `listener` (chat observer installed; per named session: alive, a listen call waiting, unread messages) |
| `arma_start(mission, hcs, client, overrides)` | Boot a mission profile from `harness.toml`. `client=true` opens a rendering game window. `overrides` sets mission context values before the first round. |
| `arma_stop` | Stop the run (or detach from an attached game) |
| `arma_hc_start`, `arma_client_start` | Add a headless client (for example, JIP) or a rendering client to a running server |
| `arma_attach(pid?)` | Attach to a game you started yourself (SP, Eden preview, hosted MP) with `@Pythia` and `@brmh` loaded |
| `arma_exec(code, target, args, scheduled)` | Run SQF. `target` is `server`, `clients`, `hcs`, `all`, `interface`, `owner:N` or `player:<name>`. Returns per-machine results and attributed errors (`aborted` when an error stopped the code). |
| `arma_events(since, kinds, types, wait_s)` | Cursor-based event stream: `evt` (types `fsm`, `ctx`, `cmd`, `ctrl_evt`, `gui`, `attached`), `err`, `res`, `hello`, `bye`, `ext`, `mission` |
| `arma_wait_for(match, since, timeout_s)` | Block until an event matches, e.g. `{"k":"evt","type":"fsm","dir":"enter","state":"GAME"}`. Supports the operators `$in`, `$re`, `$contains`, `$gt`, `$exists`, … |
| `arma_errors` | Script errors from every machine: request id, file, line, nearby code, stack |
| `arma_rpt(machine, grep)` | Raw RPT lines (`server`, `hc1`, `client1`, …) |
| `arma_snapshot(camera_pos, camera_target)` | In-engine screenshot, GUI included, optionally from a temporary camera. Returns the image and warns about black frames. |
| `arma_gui_text` | Readable text of visible controls on interface machines. Display 46 is the mission HUD; others may be background displays (main menu, role assignment). |
| `arma_map` | Terrain map as SVG, plus named locations in world coordinates (works headless) |
| `arma_set_name(name)` | The name this session answers to in game, e.g. "Zeus" (default "Claude", or `BRMH_AGENT_NAME`). Several sessions can listen at once, each under its own name and colour; `everyone, ...` reaches all of them. A name held by another live session is refused. |
| `arma_listen(since, timeout_s)` | Wait for a player to type a chat message addressed to this session (`zeus, ...`, `@zeus ...`, `hey zeus ...`, or `everyone, ...`). Shows an instant "thinking..." hint; returns the message, kills since `since`, and the next cursor. Blocks for up to `timeout_s` (default 25, under client tool timeouts); `0` checks without waiting. Chat is captured between calls, so nothing is missed. See [docs/DEMO.md](docs/DEMO.md). |
| `arma_say(text, hint?)` | Reply in game as this session: a chat line on its own radio channel and colour, optionally also a hint box |
| `arma_view(radius)` | The player's view as data: position, grid, world time and weather, and on-screen buildings, vehicles and units with screen coordinates, line of sight and building positions |
| `arma_reload(path, function?)` | Hot-reload a file from the mission source folder. Refuses files with load-time side effects unless `force`. |
| `arma_run_scenario(path)` | Run a YAML scenario; returns pass/fail and writes a markdown report |
| `rounds_state`, `rounds_context_get` / `rounds_context_set`, `rounds_fire_event`, `rounds_gui` | The rounds framework, through its own accessors |

### CLI

The CLI mirrors the tools and prints JSON, so agents without MCP (or plain scripts) can use it too. `--help` lists every command. Examples:

```powershell
$h = "host\.venv\Scripts\arma-harness.exe"
& $h start --mission rounds_framework --hcs 1 --client --override ROUND_DURATION=4
& $h exec "count allUnits" --target all
& $h wait '{"k":"evt","type":"fsm","dir":"enter","state":"ROUND_END"}' --timeout 60
& $h snapshot --camera 4480,3800,25 --look 4500,3820,0
& $h scenario timeout_round
& $h listen --name Zeus --since 0 --timeout 25   # wait for "Zeus, ..." (or "everyone, ...")
& $h say "On it." --sender Zeus
& $h guide                              # the agent cheat sheet
& $h setup-agents codex opencode --dry-run
& $h stop
```

## Missions and adapters

**Mission profiles** give each mission a name, plus its source folder, its server, client and headless-client mods, and its adapters. They are read from these files, in order:
1. `harness.toml` (checked in): the `selftest` profile and a commented example;
2. `harness.local.toml` next to it (git-ignored): your own missions and `[harness] default_mission`;
3. `%LOCALAPPDATA%\arma-harness\harness.toml`;
4. `$BRMH_CONFIG`.

Later files replace earlier profiles of the same name.

A run **copies** the mission into the server root, adding `skipLobby`, `briefing = 0` and `allowFunctionsRecompile` to the copy only.
- **Why copy:** the engine locks every file it reads, so running from the live folder would block your editor.
- **Headless clients** need `HeadlessClient_F` slots in `mission.sqm`.

**Adapters** add mission-specific observers and tools. `rounds_framework` contributes three things:
- **Hooks:** it changes no framework code, and emits these event types:
  - `fsm`, from the FSM's CBA state events;
  - `ctx`, from a wrapper around `#SET_CONTEXT_VALUE`;
  - `ctrl_evt`, from the server's `CTRL_EVENT_SEQ` events;
  - `cmd`, from the command registry event on every machine;
  - `gui`, from wrappers around `fnc_GUIAction` and `fnc_GUIEvent` on interface machines.
- **Overrides:** it applies `overrides` before the first round.
- **Tools:** it adds the `rounds_*` tools.

The hooks are installed at **preInit**, through the bridge's boot payload, so no state transition is missed.

## Scenarios

YAML files in `scenarios/` are the regression suite, and also the mission QA bot:

```yaml
name: timeout round
mission: rounds_framework
start: {overrides: {ROUND_DURATION: 4, MAX_ROUNDS: 2}}
steps:
  - wait_for: {match: {k: evt, type: fsm, dir: enter, state: ROUND_END}, timeout_s: 120}
  - assert: {context: {key: ROUNDS_DATA, match: {0.ENDING_REASON: TIME_LIMIT, 0.END_TIME: {$gt: 0}}}}
  - assert: {no_errors: true}
```

- **Step kinds:** `wait_for`, `exec` (`expect`, `expect_error`, `expect_error_count`, `expect_first_error`, `expect_owners`), `assert` (`context`, `sqf`, `event`, `sequence`, `no_errors`), `sleep`, `snapshot`, `hc_start`, `client_start`, `fire_event`, `context_set`, `reload`.
- **Scenarios in the repo:**
  - `selftest`: the harness itself, on the bundled mission;
  - `attached_check`: certifies whatever game is attached or running;
  - `boot`, `timeout_round`, `all_targets` and `jip`: the rounds framework's seed scenarios, which need a `rounds_framework` profile.

## Commander mode

An LLM commands AI squads in a battle it can't see. It knows only what its squads report by radio, as bearings and rough ranges, and orders them by grid, marker or building id: moves, building clearing, vehicles, fire missions, air support and casualty care. The harness scores each battle and replays it afterwards, the commander's picture beside the truth. It runs in a locked-down agent session with its own MCP server: Claude Code, woken by channels, or OpenCode (`--client opencode`), which signs in to most other vendors' subscriptions and API keys.

```powershell
host\.venv\Scripts\arma-harness.exe commander list                                # every scenario
host\.venv\Scripts\arma-harness.exe commander start llm_hidden_gun --seed 116     # set one up; it prints the launch command
host\.venv\Scripts\arma-harness.exe commander compare llm_hidden_gun              # afterwards, battles side by side
```

| Doc | What's in it |
|---|---|
| [COMMANDER_BENCHMARK.md](docs/COMMANDER_BENCHMARK.md) | Running battles with real LLMs, the fixed seeds, and reading the scores |
| [COMMANDER.md](docs/COMMANDER.md) | The design: turns and waking, orders, reports, the fog, operating a battle |
| [COMMANDER_MODEL.md](docs/COMMANDER_MODEL.md) | The formal model, its order table and state charts (tested against the code) |
| [COMMANDER_SCENARIOS.md](docs/COMMANDER_SCENARIOS.md) | Scenarios that test the commander's judgement |
| [COMMANDER_FIRE_SUPPORT.md](docs/COMMANDER_FIRE_SUPPORT.md), [COMMANDER_CASEVAC.md](docs/COMMANDER_CASEVAC.md), [COMMANDER_CAS.md](docs/COMMANDER_CAS.md) | Fire missions, casualties, and air support: designs and engine findings |

## Tests

| Command | Covers |
|---|---|
| `tools/build.py --check` | `cargo test`, `hemtt check`, the bridge tests under Pythia's embedded Python 3.10, `pytest` and `ruff` |
| CI (`.github/workflows/ci.yml`) | The same offline checks on a Windows runner: Rust `fmt` + `clippy -D warnings` + tests, ruff + pytest, the bridge on Python 3.10, `hemtt check` |
| `host/tests/live_attach.py` | Attach mode (needs the game) |
| `scenarios/` | The live suite (needs the game) |

## Safety

- **Network:** loopback only, with a random per-run token checked in constant time. The server config sets `loopback = 1` (LAN mode, off Steam's server list) and `BattlEye = 0`.
- **Activation:** the probe activates only for a game process whose PID has a session file in the harness home. Loading the mod alone does nothing.
- **Audit:** every SQF request is logged to `logs\audit.jsonl`.
- **Scope:** for your own machine and servers only. Never load `@brmh` on public servers.
