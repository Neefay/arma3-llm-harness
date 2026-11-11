"""How commander commands look in a terminal, with Rich. Only for people: piped or with --json, the same results print
as JSON, which is what assistants and scripts read."""
from __future__ import annotations

from rich.console import Console, Group
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

MARKS = {"ok": ("✓", "green"), "fail": ("✗", "red"), "warn": ("!", "yellow"), "info": ("•", "cyan")}
CLIENT_NAMES = {"claude": "Claude Code", "opencode": "OpenCode"}


def _console() -> Console:
    return Console(highlight=False)


def doctor(result: dict) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)
    table.add_column(style="bold", no_wrap=True)
    table.add_column(overflow="fold")  # a path has no spaces to wrap at
    for check in result["checks"]:
        mark, colour = MARKS.get(check["status"], ("?", "white"))
        detail = Text(check["detail"])
        if check.get("where"):
            detail.append("\n" + check["where"], style="dim")
        if check.get("fix"):
            detail.append("\n→ " + check["fix"], style="dim")
        table.add_row(Text(mark, style=f"bold {colour}"), check["name"], detail)
    title = f"Commander pre-flight · {CLIENT_NAMES.get(result['client'], result['client'])}"
    border = "green" if result["ok"] else "red"
    console = _console()
    console.print(Panel(table, title=f"[bold]{title}[/]", title_align="left", border_style=border, padding=(1, 2)))
    console.print(f"[{'green' if result['ok'] else 'red'}]{escape(result['next'])}[/]")


def start(result: dict) -> None:
    facts = Table.grid(padding=(0, 2))
    facts.add_column(style="dim", no_wrap=True)
    facts.add_column(overflow="fold")
    rows = [("Scenario", f"[bold]{escape(result['scenario'])}[/]  seed {result['seed']}, {result['mode']} mode"),
            ("Battle", f"run {result['run']}, attempt {result['attempt']}"),
            ("Client", CLIENT_NAMES.get(result["client"], result["client"]))]
    if result.get("model"):
        rows.append(("Model", f"[bold]{escape(result['model'])}[/]"))
    if result.get("session"):
        rows.append(("Session", escape(result["session"])))
    rows += [("Workspace", escape(result["workspace"])), ("Records", escape(result["records"]))]
    if result.get("observer"):
        rows.append(("Observer", "a game window is opening in the observer slot"))
    for key, value in rows:
        facts.add_row(key, value)
    parts: list = [facts]
    if result.get("launch"):
        parts += [Text(""), Text("Launch the commander", style="bold"),
                  Panel(Text(result["launch"]), border_style="dim", padding=(0, 1))]
    after = Table.grid(padding=(0, 2))
    after.add_column(style="bold", no_wrap=True)
    after.add_column()
    after.add_row("Next", result["then"])
    parts += [Text(""), after]
    console = _console()
    console.print(Panel(Group(*parts), title="[bold]Battle set up[/]", title_align="left", border_style="green",
                        padding=(1, 2)))


def error(message: str) -> None:
    _console().print(Panel(Text(message), title="[bold]Couldn't do that[/]", title_align="left", border_style="red",
                           padding=(0, 1)))
