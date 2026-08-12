"""Command output. A command that answers with a resource prints one
pretty-printed JSON value; `login` and `logout` report prose instead, and
style it through the helpers here so every colour the CLI emits has one
owner. Typer drops the escapes when it is not writing to a terminal, so
piped output stays plain."""

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel

from albus_cli import docs

# Wide enough for the labels `login` prints, so their values line up.
_LABEL = 12


def emit(value: BaseModel | dict[str, Any]) -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)

    print(json.dumps(value, indent=2))


def progress(message: str) -> None:
    """What the CLI is about to do, before it takes long enough that the
    reader wonders whether it hung."""
    typer.secho(message, bold=True)


def done(message: str) -> None:
    """The outcome a command was run for."""
    typer.secho("✓ ", fg=typer.colors.GREEN, bold=True, nl=False)
    typer.secho(message, bold=True)


def field(label: str, value: str) -> None:
    """A detail of that outcome, subordinate to it."""
    typer.secho(f"  {label:<{_LABEL}}", fg=typer.colors.BRIGHT_BLACK, nl=False)
    typer.echo(value)


def link(url: str) -> None:
    """A URL for the reader to act on, set apart from the prose around
    it: an authorization URL is long enough to be mistaken for one."""
    typer.secho(f"  {url}", fg=typer.colors.CYAN)


def suggest(label: str, *lines: str) -> None:
    """The reader's next move, spelled out to be run or pasted. It is
    set off by a blank line because it is where attention lands: the
    last thing `login` prints is what the reader does next."""
    typer.echo()
    typer.secho(label, bold=True)
    for line in lines:
        typer.secho(f"  {line}", fg=typer.colors.CYAN)


def documentation() -> None:
    """Both documentation URLs, for both readers of this output."""
    typer.echo()
    field("Docs", docs.SITE)
    field("Agents", docs.AGENTS)


def note(message: str) -> None:
    """Something true that the reader did not ask about and would rather
    know: a session that cannot be renewed, an ignored credential."""
    typer.secho("! ", fg=typer.colors.YELLOW, bold=True, nl=False)
    typer.echo(message)


def error(message: str) -> None:
    """What went wrong, and where every message the CLI reports is
    documented — the reader who cannot act on the sentence, agent or
    not, has one page to go to."""
    typer.secho(f"albus: {message}", fg=typer.colors.RED, err=True)
    typer.secho(
        f"albus: docs: {docs.TROUBLESHOOTING}",
        fg=typer.colors.BRIGHT_BLACK,
        err=True,
    )


def abbreviated(path: Path) -> str:
    """A path spelled as the reader would say it aloud."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)
