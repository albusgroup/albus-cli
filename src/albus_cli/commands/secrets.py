"""`albus secrets` — manage secrets available to agent sessions."""

import sys
from typing import Annotated

import typer

from albus_cli.context import sdk
from albus_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="Manage secrets.")

Name = Annotated[str, typer.Argument(metavar="NAME", help="Secret name.")]
Value = Annotated[
    str | None,
    typer.Option(
        "--value",
        help="Secret value. Omit to read it from stdin, keeping it out "
        "of the shell history.",
    ),
]


def secret_value(value: str | None) -> str:
    if value is not None:
        return value

    read = sys.stdin.read().strip()
    if not read:
        raise typer.BadParameter("no secret value on stdin")

    return read


@app.command("list")
def list_secrets(ctx: typer.Context) -> None:
    """List all secrets with masked values."""
    emit(sdk(ctx).secrets.list_secrets())


@app.command("create")
def create(ctx: typer.Context, name: Name, value: Value = None) -> None:
    """Create a secret."""
    emit(sdk(ctx).secrets.create_secret(name=name, value=secret_value(value)))


@app.command("get")
def get(ctx: typer.Context, name: Name) -> None:
    """Get a secret's masked value."""
    emit(sdk(ctx).secrets.get_secret(name=name))


@app.command("update")
def update(ctx: typer.Context, name: Name, value: Value = None) -> None:
    """Replace a secret's value."""
    emit(sdk(ctx).secrets.update_secret(name=name, value=secret_value(value)))


@app.command("delete")
def delete(ctx: typer.Context, name: Name) -> None:
    """Delete a secret."""
    sdk(ctx).secrets.delete_secret(name=name)
