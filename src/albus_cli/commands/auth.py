"""Signing in and out, and naming who is signed in.

`login` and `logout` are the documented exception to one command, one
SDK operation: they talk to Auth0 rather than to Albus. See
`AGENTS.md`.
"""

from typing import Annotated

import typer

from albus_cli import client, credentials, docs, oauth, output
from albus_cli.context import base_url, signed_in_sdk, timeout

NoBrowser = Annotated[
    bool,
    typer.Option(
        "--no-browser",
        help="Print the sign-in URL instead of opening it. For a host "
        "with no browser, and for an agent signing in the user in front "
        "of one.",
    ),
]


def login(ctx: typer.Context, no_browser: NoBrowser = False) -> None:
    """Sign in through the browser and store the session."""
    api = base_url(ctx)
    tenant = oauth.tenant_config(api)
    if no_browser:
        output.progress("Open this URL to sign in:")
        tokens = oauth.authorize(tenant, output.link, open_browser=False)
    else:
        output.progress("Opening your browser to sign in.")
        tokens = oauth.authorize(tenant, _fallback)

    session = client.credential(tokens, None)
    credentials.save(api, session)

    # Read the account back through the session just stored, not through
    # precedence: naming the API key's account would be a false report.
    signed_in = client.bearer_client(api, timeout(ctx), session)
    output.done(f"Signed in as {signed_in.auth.whoami().email}")
    output.field("API", api)
    output.field("Credential", output.abbreviated(credentials.path()))
    if session.refresh_token is None:
        output.note(
            "Auth0 issued no refresh token, so this session ends when the "
            "access token expires: enable Allow Offline Access on the API."
        )

    _also(client.shadows_session())
    _next_steps()


def logout(ctx: typer.Context) -> None:
    """Forget the stored session for this API."""
    api = base_url(ctx)
    credentials.delete(api)
    output.done(f"Signed out of {api}")
    _also(client.shadows_logout())


def whoami(ctx: typer.Context) -> None:
    """Show the signed-in account and its organizations."""
    output.emit(signed_in_sdk(ctx).auth.whoami())


def _next_steps() -> None:
    """The last lines a successful sign-in prints, where attention is
    highest: the one command that runs an agent, and the sentence to
    paste into a coding agent so the reader does not have to invent
    it."""
    output.suggest(
        "Try it:",
        'albus sessions run demo -p "hello" --agent-name demo '
        "--model gemini-3.6-flash",
    )
    output.suggest(
        "Or hand it to your coding agent:",
        f'"Albus is installed and I am signed in. Read {docs.AGENTS} '
        'and build me a working example."',
    )
    output.documentation()


def _fallback(authorization: str) -> None:
    """The authorization URL, for a reader whose browser did not open.
    The blank line after it separates waiting from the outcome, which
    arrives whenever the reader finishes signing in."""
    typer.echo("If it does not open, visit:")
    output.link(authorization)
    typer.echo()


def _also(note: str | None) -> None:
    if note:
        output.note(note)
