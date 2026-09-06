"""`albus invites` — the pending invitations into the active organization.

`/organization/invites` is `bearerAuth`-only, like `/tokens`: an API key
cannot invite a user, so these commands take the browser session with
`signed_in_sdk`.
"""

from typing import Annotated, Literal

import typer

from albus_cli.context import signed_in_sdk
from albus_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="Invite users by email.")

Role = Literal["admin", "member"]

InviteID = Annotated[
    str, typer.Argument(metavar="ID", help="The invitation ID.")
]


@app.command("list")
def list_invites(ctx: typer.Context) -> None:
    """List pending invitations. Requires the admin role."""
    emit(signed_in_sdk(ctx).invites.list_invites())


@app.command("create")
def create(
    ctx: typer.Context,
    email: Annotated[
        str,
        typer.Argument(
            metavar="EMAIL", help="Email address of the person to invite."
        ),
    ],
    role: Annotated[
        Role | None,
        typer.Option(
            "--role",
            help="Role the invitee joins with. Defaults to member.",
        ),
    ] = None,
) -> None:
    """Invite a user to join your active organization."""
    emit(signed_in_sdk(ctx).invites.create_invite(email=email, role=role))


@app.command("revoke")
def revoke(ctx: typer.Context, invite_id: InviteID) -> None:
    """Revoke a pending invitation. Requires the admin role."""
    signed_in_sdk(ctx).invites.revoke_invite(id=invite_id)
