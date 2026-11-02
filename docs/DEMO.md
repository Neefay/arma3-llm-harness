# Demo: talk to Claude from inside the game

You play. You type to Claude in the in-game chat. Claude looks at your screen, reads the world around you, changes it, and answers in chat.

Nothing here is scripted. No trigger maps "sniper" to a spawn function, and no table of hints exists. Each request is:
- free text;
- resolved against what is actually in front of you (a screenshot, plus the objects behind it);
- carried out with SQF that Claude writes on the spot.

That is the part a heuristic mission script can't do.

## Setup (about 5 minutes)

1. **Launch Arma 3** from the Launcher with `@CBA_A3`, `@Pythia` and the local mod `%LOCALAPPDATA%\arma-harness\mods\@brmh`, with BattlEye off.
2. **Open the demo mission.** In Eden, open `brmh_demo` (Altis); it is in this repo's `missions/` folder, so copy it to your profile's `missions` folder.
   - Use **Play → Play in Multiplayer** and host a LAN game; the harness is built around a server.
   - You spawn as a squad leader with two AI squadmates, on a slope 250 m north-east of Athira, facing the town.
3. **Attach the harness:** `host\.venv\Scripts\arma-harness.exe attach`. Optionally run `arma-harness scenario attached_check`.
4. **Tell Claude Code to start listening.** It loops on `arma_listen` (or `arma-harness listen --since <next>`): it handles each message, replies with `arma_say`, and listens again.

Talk to Claude by starting a chat message (any channel) with `claude`, `@claude` or `hey claude`. A "Claude thinking..." hint appears at once. The answer takes 10 to 40 seconds, so cut the waits in the edit.

## Run of show (about 3 minutes of footage)

| # | You type | What happens | Why it's the LLM part |
|---|---|---|---|
| 1 | `claude, what do you see?` | Claude describes the town in front of you, landmark by landmark ("the cream two-storey with the red roof on the left"), with the place name, time and weather. | Vision, plus world data, plus ordinary language. |
| 2 | `claude, hide a sniper in one of those houses. don't tell me which` | A marksman appears in a building that can see you, at an upper position, holding fire until you get close. | "Those houses" means the ones on your screen. Claude resolves them with `arma_view` and line-of-sight checks. |
| 3 | `claude, I can't find him, give me a hint` | A hint about that particular building: the colour of its shutters, its balcony, what it stands next to. | Claude looks at the building it chose and describes it. No hint list exists. |
| 4 | `claude, make this feel like a horror movie` | Full-moon night, rolling fog, maybe flashlights instead of night vision, a sound in the dark. Claude decides. | An open-ended creative brief turned into engine settings. |
| 5 | (fight, die or win) `claude, what happened?` | An after-action report from the kill events: who shot whom, with what, from how far, with some commentary. | Narrating real events. |

**Bonus prompts** (let your friends suggest some):
- `claude, have Roberts and Turner clear that house from the back`
- `claude, which window is he in?` (Claude zooms a camera on the building)
- `claude, make it 1944`

## Recording tips

- Record the game window with your usual recorder (OBS or ShadowPlay). The harness only captures frames for Claude.
- Keep the Claude Code terminal visible in a corner if you want to show the "how".
- Type one sentence per message. The chat feed shows roughly one line of reply comfortably; longer answers go to a hint box.

## How it works

```
you type "claude, ..."  -> HandleChatMessage on your machine -> evt type=chat -> arma_listen returns
Claude: arma_view (objects on screen, positions, line of sight) + arma_snapshot (the frame)
     -> arma_exec (SQF it writes for this request, on the server or your machine)
     -> arma_say (reply on Claude's own radio channel)
     -> arma_listen(since=next)
kills -> EntityKilled on the server -> evt type=killed -> returned with the next message
```

The observers are installed by `arma_listen`. Re-running them replaces the handlers, so they survive harness restarts. After a mission restart, the next `arma_listen` reinstalls them.
