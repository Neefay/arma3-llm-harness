"""Chat that wakes the assistant: a player's message to it starts its turn, instead of a listen loop.

With arma_listen the agent hears chat only while a call is running, and every call that times out costs a model turn.
Here a thread in the MCP server waits on the game's chat the whole time and, when a message is addressed to this
session's name, has the client start a turn with it: Claude Code through a channel notification (the server declares
`claude/channel`, and Claude Code must be launched with `--dangerously-load-development-channels server:arma`),
OpenCode by posting the message into its session through OpenCode's server. Between messages nothing runs and nothing
is billed.

The thread survives the game going away: it waits, and carries on once a game is attached or started again.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

RETRY_S = 5.0
WAIT_S = 60.0  # one listen at a time; chat said between two is picked up by the next, from the cursor


def wake_text(message: dict, kills: list[dict], name: str) -> tuple[str, dict, str]:
    """What the agent is told, the meta for its channel tag, and the one line a person sees in OpenCode's app."""
    sender, text = message.get("name") or "A player", (message.get("text") or "").strip()
    lines = [f"{sender}: {text}"]
    if kills:
        lines += ["", "Deaths since the last message:"]
        for kill in kills[-10:]:
            by = f" by {kill['killer']}" if kill.get("killer") and kill.get("killer") != kill.get("victim") else ""
            how = ", ".join(str(part) for part in (kill.get("weapon"), f"{kill['distance']} m"
                                                   if kill.get("distance") is not None else None) if part)
            lines.append(f"- {kill.get('victim', '?')}{by}" + (f" ({how})" if how else ""))
    lines += ["", f"You are {name}. Answer in game with arma_say, then end your turn: the next message to you starts "
                  "a new one. Don't call arma_listen while chat wakes are on."]
    meta = {"from": sender, "to": name, "seq": str(message.get("seq", ""))}
    return "\n".join(lines), meta, f"💬 {sender} → {name}: {text}"


class ChatWake:
    """Waits on the game's chat on a thread of its own and calls ``deliver(text, meta, display)`` for each message
    addressed to ``name()``. ``listen`` is Harness.listen of a harness used only by this thread."""

    def __init__(self, listen: Callable[..., dict], name: Callable[[], str],
                 deliver: Callable[[str, dict, str], None], log: Callable[[str], None]):
        self.listen, self.name, self.deliver, self.log = listen, name, deliver, log
        self.stop = threading.Event()
        self.cursor: int | None = None
        self.delivered = 0
        self.problem: str | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> ChatWake:
        self.thread.start()
        return self

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                result = self.listen(name=self.name(), since=self.cursor, timeout=WAIT_S)
            except Exception as exc:  # no game, or it went away: wait for one, from where we were
                if self.problem != str(exc):
                    self.log(f"chat wake: waiting for a game ({exc})")
                self.problem = str(exc)
                self.stop.wait(RETRY_S)
                continue
            self.problem = None
            self.cursor = result.get("next", self.cursor)
            if self.stop.is_set() or not result.get("found"):
                continue
            text, meta, display = wake_text(result["message"], result.get("kills") or [], self.name())
            try:
                self.deliver(text, meta, display)
                self.delivered += 1
            except Exception as exc:
                self.log(f"chat wake: a message couldn't be delivered: {exc}")
                time.sleep(1)
