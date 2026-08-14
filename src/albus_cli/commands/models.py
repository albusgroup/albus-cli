"""`albus models` — the models a session can run on.

The name a `sessions run` passes to `--model` has to be one of these, and
the pair names the provider it runs on, which is the credential
`--credential` has to carry.
"""

import typer

from albus_cli.context import sdk
from albus_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="List supported models.")


@app.command("list")
def list_models(ctx: typer.Context) -> None:
    """List the supported models and the provider each runs on."""
    emit(sdk(ctx).models.list_models())
