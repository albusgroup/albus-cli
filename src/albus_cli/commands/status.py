"""`albus status` — the credential in effect, and whether Albus accepts
it.

Every other command answers that question only by failing, which a
coding agent has to read English to interpret. This one answers it in
JSON before anything is attempted: which API, which of the two
credentials will be sent, whether it works, and who it belongs to.
"""

from importlib.metadata import version
from typing import Any

import httpx
import typer
from albus_sdk import errors

from albus_cli import client, credentials, oauth, output
from albus_cli.context import base_url, timeout

# Everything that answers "the credential does not work": Albus refusing it, a
# stored session that cannot be renewed, an Auth0 tenant that is unconfigured
# or unreachable, and an API that is not answering.
REFUSED = (
    errors.AlbusError,
    client.NotSignedIn,
    oauth.LoginError,
    httpx.HTTPError,
)

# What the report names as the credential the next command will send.
API_KEY = "api_key"
SESSION = "session"
NONE = "none"


def status(ctx: typer.Context) -> None:
    """Report the credential in effect and whether Albus accepts it."""
    api = base_url(ctx)
    credential = _credential(api)
    report: dict[str, Any] = {
        "cli_version": version("albus-cli"),
        "base_url": api,
        "credential": credential,
        "authenticated": False,
    }

    if credential == NONE:
        output.emit(report)
        return

    try:
        report.update(_accepted(ctx, api, credential))
    except REFUSED as refused:
        # A credential that does not work is this command's answer, not its
        # failure: reporting it as an error would make the one command an
        # agent runs to find out where it stands exit non-zero whenever
        # the news is bad.
        report["error"] = _refusal(refused)

    output.emit(report)


def _credential(api: str) -> str:
    """Which credential the next command sends, in the order `client`
    resolves them."""
    if client.api_key():
        return API_KEY

    if credentials.load(api) is not None:
        return SESSION

    return NONE


def _accepted(ctx: typer.Context, api: str, credential: str) -> dict[str, Any]:
    """What Albus says about the credential. The session is asked who it
    belongs to; an API key is org-scoped and `/whoami` refuses it, so it
    is spent on the cheapest operation it can authenticate instead, and
    the report carries no identity for it."""
    if credential == API_KEY:
        client.client(api, timeout(ctx)).sessions.list_sessions()
        return {"authenticated": True}

    signed_in = client.signed_in_client(api, timeout(ctx)).auth.whoami()
    return {
        "authenticated": True,
        "email": signed_in.email,
        "organizations": [
            organization.model_dump(mode="json", exclude_none=True)
            for organization in signed_in.organizations
        ],
    }


def _refusal(refused: Exception) -> str:
    """Why the credential does not work, in the words of whatever said so:
    the server, the credential store, or Auth0."""
    if isinstance(refused, errors.AlbusError):
        return f"{refused.status_code}: {refused.message}"

    return str(refused)
