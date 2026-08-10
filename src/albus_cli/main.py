"""`albus` — command-line client for the Albus REST API."""

from typing import Annotated

import httpx
import typer
from albus_sdk import errors

from albus_cli.client import BASE_URL_ENV, MissingAPIKey
from albus_cli.commands import agents, secrets, sessions
from albus_cli.context import Options, sdk
from albus_cli.output import emit

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Command-line client for the Albus REST API. Authenticates with "
    "the API key in ALBUS_API_KEY and prints JSON responses.",
)
app.add_typer(sessions.app, name="sessions")
app.add_typer(secrets.app, name="secrets")
app.add_typer(agents.app, name="agents")


@app.callback()
def configure(
    ctx: typer.Context,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            envvar=BASE_URL_ENV,
            help="Albus API base URL. Defaults to production.",
        ),
    ] = None,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Request timeout in seconds."),
    ] = 30.0,
) -> None:
    ctx.obj = Options(base_url=base_url, timeout=timeout)


@app.command("health")
def health(ctx: typer.Context) -> None:
    """Check service availability."""
    emit(sdk(ctx).health.health())


def main() -> None:
    try:
        app()
    except MissingAPIKey as missing:
        fail(str(missing))
    except errors.AlbusError as error:
        fail(f"{error.status_code}: {error.message}")
    except httpx.HTTPError as transport:
        fail(str(transport))


def fail(message: str) -> None:
    typer.secho(f"albus: {message}", fg=typer.colors.RED, err=True)
    raise SystemExit(1)
