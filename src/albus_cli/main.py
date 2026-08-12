"""`albus` — command-line client for the Albus REST API."""

import json
from http import HTTPStatus
from importlib.metadata import version
from typing import Annotated

import httpx
import typer
from albus_sdk import errors

from albus_cli import client, credentials, docs, oauth, output
from albus_cli.client import API_KEY_ENV, BASE_URL_ENV, NotSignedIn
from albus_cli.commands import (
    agents,
    auth,
    invites,
    secrets,
    sessions,
    status,
    tokens,
)
from albus_cli.context import Options, public_sdk

BETA_CONTACT = "carlo@albus.sh"

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Command-line client for the Albus REST API. Authenticates with "
    f"`albus login` or the API key in {API_KEY_ENV}, and prints JSON "
    "responses.",
    # Both readers of this help get the URL that is theirs: a person the
    # site, a coding agent the page written for it to execute.
    epilog=f"Docs: {docs.SITE}  Agents: {docs.AGENTS}",
)
app.add_typer(sessions.app, name="sessions")
app.add_typer(secrets.app, name="secrets")
app.add_typer(agents.app, name="agents")
app.add_typer(tokens.app, name="tokens")
app.add_typer(invites.app, name="invites")
app.command("login")(auth.login)
app.command("logout")(auth.logout)
app.command("whoami")(auth.whoami)
app.command("status")(status.status)


def _version(shown: bool) -> None:
    """The installed version, before any command runs: it is what a
    reader reports a bug against, and what an agent checks a documented
    flag against."""
    if not shown:
        return

    typer.echo(version("albus-cli"))
    raise typer.Exit


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
    show_version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Print the CLI version and exit.",
            callback=_version,
            is_eager=True,
        ),
    ] = False,
) -> None:
    ctx.obj = Options(base_url=base_url, timeout=timeout)


@app.command("health")
def health(ctx: typer.Context) -> None:
    """Check service availability."""
    # `/health` has no `security` in the spec, so it answers before the
    # reader has signed in — which is when they run it.
    output.emit(public_sdk(ctx).health.health())


def main() -> None:
    try:
        app()
    except (NotSignedIn, oauth.LoginError) as unauthenticated:
        fail(str(unauthenticated))
    except credentials.CorruptFile as corrupt:
        fail(f"{corrupt}. Delete or repair it, then run `albus login`.")
    except errors.AlbusError as error:
        fail(_reported(error))
    except (httpx.HTTPError, errors.NoResponseError) as transport:
        fail(client.unreachable(transport))
    except OSError as unusable:
        # A read-only or differently owned config directory is ordinary
        # where agents run, and a traceback names no way out of it.
        fail(
            f"could not use {credentials.path()}: {unusable}. Fix its "
            f"permissions, or point {credentials.CONFIG_DIR_ENV} at a "
            "writable directory."
        )


def _reported(error: errors.AlbusError) -> str:
    """What the server refused, said in the terms the reader can act
    on. A 403 the server codes `not_provisioned` is a valid identity the
    beta roster does not carry, and a 401 is the credential this command
    was built with — `client` names which one that was."""
    if _not_provisioned(error):
        return (
            "this account is not in the Albus beta. Email "
            f"{BETA_CONTACT} to request access."
        )

    if error.status_code == HTTPStatus.UNAUTHORIZED:
        return client.rejected()

    if error.status_code < HTTPStatus.BAD_REQUEST:
        return client.unreadable()

    served = _body(error).get("message")
    if isinstance(served, str):
        return f"{error.status_code}: {served}"

    # The SDK's fallback message for a status the spec does not document
    # repeats the status and appends the whole body, so an HTML page from
    # a proxy arrives as a wall of markup.
    if isinstance(error, errors.AlbusDefaultError):
        return f"{error.status_code}: {_phrase(error.status_code)}"

    return f"{error.status_code}: {error.message}"


def _phrase(status: int) -> str:
    """What a status means, for a server that sent no message of its own —
    an HTML error page from a proxy, most often."""
    try:
        return HTTPStatus(status).phrase.lower()
    except ValueError:
        return "unexpected response"


def _not_provisioned(error: errors.AlbusError) -> bool:
    if error.status_code != HTTPStatus.FORBIDDEN:
        return False

    return _body(error).get("code") == "not_provisioned"


def _body(error: errors.AlbusError) -> dict[str, object]:
    """What the server said, as far as it is a JSON object."""
    try:
        body = json.loads(error.body)
    except ValueError:
        return {}

    if not isinstance(body, dict):
        return {}

    return {str(key): value for key, value in body.items()}


def fail(message: str) -> None:
    output.error(message)
    raise SystemExit(1)
