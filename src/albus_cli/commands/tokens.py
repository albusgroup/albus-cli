"""`albus tokens` — manage the organization's API keys.

`/tokens` is `bearerAuth`-only: an API key cannot mint or list a key, so
these commands take the browser session with `signed_in_sdk`.
"""

from typing import Annotated

import typer

from albus_cli.context import signed_in_sdk
from albus_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="Manage API keys.")

TokenID = Annotated[str, typer.Argument(metavar="ID", help="API key lookup ID.")]


@app.command("list")
def list_tokens(ctx: typer.Context) -> None:
    """List API keys and their metadata."""
    emit(signed_in_sdk(ctx).tokens.list_tokens())


@app.command("create")
def create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(metavar="NAME", help="API key name.")],
) -> None:
    """Create an API key. Its value is returned only in this response."""
    emit(signed_in_sdk(ctx).tokens.create_token(name=name))


@app.command("get")
def get(ctx: typer.Context, token_id: TokenID) -> None:
    """Get an API key's metadata."""
    emit(signed_in_sdk(ctx).tokens.get_token(id=token_id))


@app.command("delete")
def delete(ctx: typer.Context, token_id: TokenID) -> None:
    """Revoke an API key."""
    signed_in_sdk(ctx).tokens.delete_token(id=token_id)
