# Commander mode with OpenCode

How to run a commander battle in [OpenCode](https://opencode.ai), so the commander can be any model OpenCode can use: a ChatGPT or GitHub Copilot subscription, an API key, OpenRouter, a local model, or one of OpenCode's free models. It's written so that a person, or an assistant pointed at this repo, can set it up and run it from the commands here, without reading the code.

For what commander mode is, see the README's [Commander mode](../README.md#commander-mode) section. For running battles as a benchmark, see [COMMANDER_BENCHMARK.md](COMMANDER_BENCHMARK.md). Claude Code works too, and is covered there.

All commands run in PowerShell from the repo root.

## Contents

1. [What you need](#1-what-you-need)
2. [Check everything](#2-check-everything)
3. [Start a battle](#3-start-a-battle)
4. [While it runs, and after](#4-while-it-runs-and-after)
5. [Troubleshooting](#5-troubleshooting)
6. [How it works](#6-how-it-works)
7. [For assistants](#7-for-assistants)

## 1. What you need

- **The harness, set up**: the README's [Quick start](../README.md#quick-start-first-time), steps 1 to 3 (the prerequisites, the build with its venv and @brmh mod, and the self-test).
- **OpenCode 2 or later.** Either the desktop app or the command line. The app starts OpenCode's background server by itself; with only the command line, start it with `opencode service start`.
- **A model that can call tools,** signed in through OpenCode: in the app's settings, or with `opencode auth login`. OpenCode also lists a few free models of its own (their names end in `-free`), which need no account.

## 2. Check everything

```powershell
& "host\.venv\Scripts\arma-harness.exe" commander doctor --client opencode
```

It checks, without calling a model or starting the game:

| Check | Passes when |
|---|---|
| OpenCode | OpenCode 2 or later is installed: on the PATH, or the desktop app's own copy |
| Background server | OpenCode's server is running and the harness can sign in to it |
| Models | At least one model that can call tools is available. The list is printed: pick one from it |
| Chosen model | With `--model provider/model`, that model is in the list. A near miss gets a suggestion |
| Lockdown | A throwaway session in the commander's workspace can use the commander's tools and nothing else. It's deleted afterwards |
| Game | Information only: whether a game is running. `commander start` boots one if not |

Anything that fails comes with what to do about it. In a terminal the result is laid out as a table; piped, or with `--json`, it's JSON with `ok` and one entry per check, and the exit code is 1 if anything failed.

To check a model before using it, add it: `commander doctor --client opencode --model openai/gpt-6-luna`.

## 3. Start a battle

List the scenarios. The `llm_*` ones are the benchmark, and the others are harness tests:

```powershell
& "host\.venv\Scripts\arma-harness.exe" commander list
```

Some harness tests (`fire_check`, `contacts_check`, `orders_check` and the like) have no objective and always end on the time limit. For a battle that can be won, pick an `llm_*` scenario or `poc_a_to_b`, a five-minute one.

### In one command

```powershell
& "host\.venv\Scripts\arma-harness.exe" commander start poc_a_to_b --client opencode --model openai/gpt-6-luna
```

This:

1. Checks the model exists, before anything else.
2. Boots the game if it isn't running (a minute or two), or reuses it.
3. Sets the battle up: stations, enemies, vehicles, the commander's records.
4. Writes the commander's OpenCode workspace and restarts its MCP server, so the battle starts clean.
5. Opens a session there, titled "Commander: <scenario>, seed <n>", with the `commander` agent and the model, and sends `start`.

The commander is then playing. Add `--seed N` to replay a seed, and `--watch` to open a game window in the observer slot.

### By hand, in the app

Leave out `--model`:

```powershell
& "host\.venv\Scripts\arma-harness.exe" commander start poc_a_to_b --client opencode
```

Then in the OpenCode desktop app, open the folder it prints, `%LOCALAPPDATA%\arma-harness\commander\workspace-opencode`, as a project. Start a new session: its agent is already **commander**, since the workspace switches the others off. Pick the model, and type `start`.

## 4. While it runs, and after

- **Watching.** Open the workspace folder as a project in the desktop app and select the battle's session. Each radio wake shows as a 📻 RADIO message with the turn, the time and what woke it. **Don't type in the session**: the radio is the commander's only input, and anything typed is outside the battle.
- **Progress** without touching anything:

  ```powershell
  & "host\.venv\Scripts\arma-harness.exe" commander status
  ```

- **The end.** The commander receives "MISSION END" and ends its turn. The battle is over when `status` shows `ended`.
- **The replay**, with the commander's picture beside the truth, its words and orders, the model and its token use:

  ```powershell
  & "host\.venv\Scripts\arma-harness.exe" commander review
  ```

- **Comparing battles** of one scenario: `commander compare <scenario>`, or `--csv` for a spreadsheet.
- **Shutting the game down** when you're done: `commander stop`.

The battle's records are in `%LOCALAPPDATA%\arma-harness\runs\<run>\commander-<n>\`. Its `client.json` names the OpenCode session and holds the lockdown result checked when the battle started.

## 5. Troubleshooting

| Symptom | Cause, and what to do |
|---|---|
| `doctor`: OpenCode not found | Install OpenCode 2. If it's somewhere unusual, set `BRMH_OPENCODE_CLI` to its `opencode` or `opencode-cli` executable |
| `doctor`: background server not reachable | Open the desktop app, or run `opencode service start` |
| `doctor`: no models | Sign in to a provider in the app's settings, or with `opencode auth login` |
| `doctor`: lockdown fails | Don't run a battle: the commander could use tools outside its own, which breaks the fog. A newer OpenCode may name its permissions differently; see section 6 |
| `start`: no model 'x' | Use a name from `doctor`'s list, as `provider/model`. A variant goes after `#`, as in `openai/gpt-6-luna#high` |
| The commander never gets a turn after the first | Look at the battle's `operator.log` for lines starting `OpenCode:`. One names the session wakes go to; others say why one failed |
| `operator.log`: "2 sessions are running in the commander's workspace" | Only one session may run there at a time, since wakes can't tell them apart. Stop the other one |
| `operator.log`: THE LOCKDOWN DOESN'T HOLD | The session could use tools outside its own. Stop the battle: it doesn't count |
| The session shows the raw `<channel source="commander">` block | The battle was started by an older version of the harness. Start it again |

## 6. How it works

Claude Code has *channels*, which let an MCP server start a turn in an idle session. OpenCode has no channels, but its background server takes a prompt into a session from outside and starts a turn with it. So with `--client opencode`:

- **The workspace** is `%LOCALAPPDATA%\arma-harness\commander\workspace-opencode`, with one `opencode.json`, rewritten by every `commander start`. It holds the commander's MCP server, a `commander` agent, and the lockdown.
- **Waking.** When the commander should get a turn, its MCP server posts the briefing to OpenCode's server, as a prompt to the session running in the workspace. A briefing that arrives mid-turn waits for the turn to end. The model reads a `<channel source="commander">` block, the same as in Claude Code; the app shows a tidier version, as plain text, since the app doesn't render Markdown in user messages.
- **The lockdown.** The workspace denies every tool and allows the commander's. It does so twice: as the agent's permissions, and as policies, which are applied after any rule the app adds to a session and can only take access away. The desktop app gives every session it opens its browser, so the policies are what really hold. `doctor` and every battle check the result by asking OpenCode what the session may do.
- **Records.** The review reads the session from OpenCode's API after the battle, and keeps a copy beside the records.

The design, and the research behind choosing OpenCode, are in [COMMANDER.md](COMMANDER.md), sections 5.9 and 13.1.

## 7. For assistants

If you're an assistant asked to set up or run a commander battle in OpenCode:

1. **You're the operator, not the commander.** Run the commands above, and report what they print. Don't play the commander from your own session, and don't use the `arma_*` tools to tell it anything or change the battle while it runs.
2. **Ask before starting a game** if the user might be playing (AGENTS.md, golden rule 3).
3. **Run `doctor` first** and fix what it reports before `start`. Its JSON form (piped, or `--json`) has `ok` and a `fix` for each failed check.
4. **Ask the user which model** to use, from `doctor`'s list, unless they've said.
5. **Report the outcome from the records,** not from watching: `commander status` while it runs, `commander review` afterwards.
