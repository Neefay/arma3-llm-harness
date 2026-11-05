"""When the commander gets a turn: its own timers, debounced radio messages, and turn interruption modes.

Pure logic with no clock of its own: callers pass mission time as ``now``. A separate delivery route
(a Claude Code channel today) turns each returned Wake into a turn in the client.
"""
from __future__ import annotations

from dataclasses import dataclass, field

HOLD, DELIVER = "hold", "deliver"


@dataclass
class Wake:
    messages: int = 0
    timers: list[dict] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    fallback: bool = False  # the previous turn was assumed over, because no end-turn call came

    def reason(self) -> str:
        parts = []
        if self.notices:
            parts.append("notice")
        if self.messages:
            parts.append(f"{self.messages} message{'s' if self.messages != 1 else ''}")
        if self.timers:
            parts.append(f"{len(self.timers)} timer{'s' if len(self.timers) != 1 else ''}")
        return ", ".join(parts)


@dataclass
class WakeLogic:
    quiet_s: float = 3.0
    ceiling_s: float = 15.0
    mode: str = HOLD
    idle_s: float = 20.0
    in_turn: bool = False
    last_tool: float = 0.0
    pending: int = 0
    first_message: float = 0.0
    last_message: float = 0.0
    timers: dict[str, dict] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)
    assumed_over: bool = False
    messages_only: bool = False

    def message(self, now: float) -> None:
        if self.pending == 0:
            self.first_message = now
        self.pending += 1
        self.last_message = now

    def add_timer(self, timer_id: str, due: float, note: str) -> None:
        self.timers[timer_id] = {"id": timer_id, "due": due, "note": note}
        self.messages_only = False

    def cancel_timer(self, timer_id: str) -> bool:
        return self.timers.pop(timer_id, None) is not None

    def notice(self, text: str) -> None:
        """Something the commander must always hear: mission end, restart, a harness fault."""
        self.notices.append(text)

    def turn_started(self, now: float) -> None:
        self.in_turn, self.last_tool = True, now

    def tool_used(self, now: float) -> None:
        self.last_tool = now

    def can_end_turn(self, messages_only: bool) -> bool:
        """A commander with no follow-up set has to say it means that, or it could wait forever by accident."""
        return bool(self.timers) or messages_only

    def end_turn(self, messages_only: bool = False) -> None:
        self.in_turn = False
        self.messages_only = messages_only and not self.timers

    def no_wake_scheduled(self) -> bool:
        return not self.in_turn and not self.timers

    def poll(self, now: float) -> Wake | None:
        """The wake due now, if any. Calling it delivers: the items it returns are consumed."""
        if self.in_turn and self.mode == HOLD:
            if now - self.last_tool < self.idle_s:
                return None
            # The client's state can't be seen from here, so a quiet turn is taken to be over.
            self.in_turn = False
            self.assumed_over = True

        due = [t for t in self.timers.values() if t["due"] <= now]
        messages_ready = self.pending > 0 and (bool(self.notices) or now - self.last_message >= self.quiet_s
                                               or now - self.first_message >= self.ceiling_s)
        debouncing = self.pending > 0 and not messages_ready
        if debouncing or not (self.notices or messages_ready or due):
            return None

        wake = Wake(messages=self.pending, timers=sorted(due, key=lambda t: t["due"]),
                    notices=list(self.notices), fallback=self.assumed_over)
        for timer in due:
            del self.timers[timer["id"]]
        self.pending = 0
        self.notices, self.assumed_over = [], False
        self.turn_started(now)
        self.messages_only = False
        return wake
