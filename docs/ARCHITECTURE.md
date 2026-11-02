# Architecture

## Components

| Part | Where | Runs in | Role |
|---|---|---|---|
| SQF probe | `addons/main/functions` (HEMTT → `brmh_main.pbo`) | every game machine | **Agent:** exec, events, errors. **Hub** (server only): bridge poll, routing, machine registry. |
| In-game bridge | `python/bridge.py` (Pythia package `brmh`) | the hub's game process | Localhost HTTP endpoint; request queue; result collection; event ring buffer |
| Rust extension | `brmh_ext/` → `brmh_x64.dll` | every machine (used on renderers) | Present-hook frame capture, terrain SVG export |
| Host package | `host/src/arma_harness` | tool / agent side | Process management, mission staging, bridge client, adapters, MCP server, CLI, scenarios |

The three game-side parts ship as one mod, `@brmh`: `addons/`, `python/` and `brmh_x64.dll` at its root.

## Request path

```
host Bridge.exec ──POST /exec──▶ bridge.Hub.submit (queue, Slot)
                                      │ (game frame)  brmh.bridge.poll ◀── BRMH_fnc_onFrame (server)
                                      ▼
                    BRMH_fnc_route: resolve target → "dispatch" envelope {owners}
                      ├─ local: brmh_queue
                      └─ remote: CBA_fnc_ownerEvent "brmh_req" → agent's brmh_queue
                    BRMH_fnc_exec (next drain, unscheduled; or spawned)
                      → "begin", run, "res" {ok, r, errors, ms}
                    BRMH_fnc_emit → (client) CBA serverEvent "brmh_out" → BRMH_fnc_out
                                  → brmh.bridge.emit → Slot.results (complete when |results| = |owners|)
host ◀── HTTP response {ok, owners, results[]} ──┘
```

- **Unscheduled by default**, so a result is ready within the frame.
- **Typical round trip:** 1–2 server frames plus HTTP, about 20–60 ms locally. Remote targets add one network hop each way.
- **Timeouts:**
  - The response says whether the request was ever dispatched, which tells "the game isn't polling" apart from "a machine didn't answer".
  - `owners: []` gives an immediate "no machine matches" error rather than a wait.

## Errors

The `ScriptError` mission event handler (2.14+) attributes each error in one of two ways:
1. to `brmh_current`, the request executing right now, which is set before `compile` so compile errors count too;
2. to the `private _brmhReq = "<id>";` tag compiled into every request, which shows up in the handler's `_content` for code that request spawned.

**Aborts.** A type error aborts the rest of the frame's handler. A request still marked current on the next frame is therefore reported as `aborted`. Requests queued behind it survive, because the queue is drained one request at a time.

## Events

- **Envelopes:** single JSON objects with `k` (kind), `m`/`o` (machine kind and owner), `t` (`CBA_missionTime`), `tt` (`diag_tickTime`) and `f` (frame). The bridge adds `seq` and `epoch`.
- **Kinds:** `hello` and `bye` (registry), `dispatch`, `begin` and `res` (requests), `err`, `evt` (adapters: `fsm`, `ctx`, `cmd`, `ctrl_evt`, `gui`, `attached`), `ext` (extension callbacks), `bridge`, `mission`.
- **Storage:** the bridge keeps the last 50,000 events. `/events?since=N&wait=S` long-polls, and `dropped: true` says the cursor fell off the ring.
- **RPT mirror:** the RPT receives a copy (`[BRMH] …`, chunked at 900 characters) while the bridge is down, and always for `err` and `hello`.

## Lifecycle and activation

1. **Spawn.** `Harness.start` stages the mission copy and writes `server.cfg`, then spawns the server. Inside a job object it spawns through WMI, so the game outlives the MCP server. Right after spawning it writes `sessions/<pid>.json` with the token and the boot payload.
2. **Activate.** At preInit the hub calls `brmh.bridge.start(mission, world)` every 2 s while inactive. It activates only if its own PID has a session file, binds `127.0.0.1:0`, and writes `<pid>.port.json`.
3. **Boot payload.** Adapter SQF is sent ahead of all other requests, before the mission's `init.sqf` runs.
4. **Mission restart.** Every `start()` call while already running begins a new **epoch**: pending requests fail with "mission restarted", and the boot payload is sent again. Adapters therefore re-attach automatically.
5. **Attach.** `attach` writes a session file for a game it didn't launch, and the probe picks it up within 2 s. `stop` then only deletes the session file.

## Design decisions (and why)

| Decision | Reason (verified on 2.22) |
|---|---|
| The probe is a mod, not mission code | No mission changes; release missions can never contain it; it works with any mission |
| HTTP through Pythia, not a file inbox | A dedicated server runs a packed snapshot of the mission, and files created later are invisible |
| Missions run as staged copies | The engine locks files it read until it exits, which would block the author's editor |
| Session file per PID | Per-process opt-in; several harness servers at once; attach to a running game |
| Ephemeral bridge port | No port clashes; the port is published through the port file |
| WMI spawn inside jobs | MCP clients run servers in a KILL_ON_JOB_CLOSE job; breakaway was unreliable (a nested venv-launcher job) |
| CBA events for routing | The framework already depends on CBA; `ownerEvent` and `serverEvent` handle locality |
| Requests and results as JSON strings over Pythia | Pythia converts types lossily: a dict returns only its keys, and NaN breaks parsing. `fromJSON` returns nil for top-level scalars, so values travel wrapped in arrays |
| `loopback = 1` | LAN mode; `-ip=127.0.0.1` alone still registers with the Steam master list |
| Headless client = `arma3server_x64 -client` | `arma3_x64 -client` opens a full GUI client. HCs need a `HeadlessClient_F` slot, or they hang silently |
| Frame capture by Present vtable hook | `RVExtensionGGetR2TTexture` returns nothing for scripted render-to-texture; the hook captures exactly what is displayed |

## Extending

- **New adapter:** add SQF to `host/src/arma_harness/adapters/` and register it in `adapters.boot_items`. Emit `["evt", createHashMapFromArray [["type", ...], ...]] call BRMH_fnc_emit`. Add tools in `mcp_server.py` under a mission prefix.
- **New generic tool:** add a `Harness` method, then a thin `@server.tool()` wrapper and a CLI subcommand.
- **New probe function:** add `fn_<name>.sqf` and a `CfgFunctions` entry, in Nife's style (see the `nife-sqf-style` skill). `hemtt check` must stay clean.
