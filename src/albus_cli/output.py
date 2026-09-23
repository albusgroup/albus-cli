"""Command output. A command that answers with a resource prints one
pretty-printed JSON value — to stdout, or to the file `--output` named,
since a whole trace is more than a terminal shows; `login` and `logout`
report prose instead, and style it through the helpers here so every
colour the CLI emits has one owner. Typer drops the escapes when it is
not writing to a terminal, so piped output stays plain."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from pydantic import BaseModel

from albus_cli import docs

# Wide enough for the labels `login` prints, so their values line up.
_LABEL = 12

_destination: Path | None = None


def direct_to(path: Path | None) -> None:
    """Where `emit` writes from now on: a file, or stdout for None. The
    global options set it before every command, and a file it cannot
    write is refused there, before any request is made."""
    global _destination
    if path is not None:
        _write(path, path.touch)

    _destination = path


def emit(value: BaseModel | dict[str, Any]) -> None:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)

    text = json.dumps(value, indent=2)
    if _destination is None:
        print(text)
        return

    _write(_destination, lambda: _destination.write_text(text + "\n"))


def _write(path: Path, attempt: Callable[[], object]) -> None:
    """An `--output` file that cannot be written is the option's error,
    not the credential store's, which is what `main` makes of a stray
    OSError."""
    try:
        attempt()
    except OSError as unwritable:
        raise typer.BadParameter(
            f"cannot write {path}: {unwritable.strerror}",
            param_hint="--output",
        ) from unwritable


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


def upgrade_available(package: str, installed: str, latest: str) -> None:
    """A newer release exists. On stderr, after the command's own
    output, so a piped JSON response stays JSON."""
    typer.secho(
        f"albus: {package} {latest} is available (installed {installed}). "
        f"Upgrade with `uv tool upgrade {package}` or "
        f"`pip install --upgrade {package}`.",
        fg=typer.colors.YELLOW,
        err=True,
    )


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
