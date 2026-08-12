"""`albus invites` — invite a person to Albus.

`/invites` is `bearerAuth`-only, like `/tokens`: an API key cannot invite a
user, so these commands take the browser session with `signed_in_sdk`.
"""

from typing import Annotated

import typer

from albus_cli.context import signed_in_sdk
from albus_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="Invite users by email.")


@app.command("create")
def create(
    ctx: typer.Context,
    email: Annotated[
        str,
        typer.Argument(
            metavar="EMAIL", help="Email address of the person to invite."
        ),
    ],
) -> None:
    """Invite a user, who gets their own organization.

    `CreateInviteRequest` also takes `role` and `organization_id`, which
    are left to the API's defaults: one user is one organization for the
    beta, so there is no second organization to name or role to choose.
    """
    emit(signed_in_sdk(ctx).invites.create_invite(email=email))
