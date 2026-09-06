"""`albus organization` — the organization the commands act in, and its
members."""

from typing import Annotated, Literal

import typer

from albus_cli.context import sdk
from albus_cli.output import emit

app = typer.Typer(
    no_args_is_help=True, help="Manage the organization and its members."
)

Role = Literal["admin", "member"]

UserID = Annotated[
    str, typer.Argument(metavar="USER_ID", help="The member's user ID.")
]


@app.command("get")
def get(ctx: typer.Context) -> None:
    """Get the organization."""
    emit(sdk(ctx).organization.get_organization())


@app.command("rename")
def rename(
    ctx: typer.Context,
    name: Annotated[
        str, typer.Argument(metavar="NAME", help="New display name.")
    ],
) -> None:
    """Rename the organization. Requires the admin role."""
    emit(sdk(ctx).organization.update_organization(name=name))


@app.command("members")
def members(ctx: typer.Context) -> None:
    """List the organization's members. Requires the admin role."""
    emit(sdk(ctx).organization.list_organization_members())


@app.command("set-role")
def set_role(
    ctx: typer.Context,
    user_id: UserID,
    role: Annotated[
        Role, typer.Argument(metavar="ROLE", help="admin or member.")
    ],
) -> None:
    """Set a member's role. Requires the admin role."""
    emit(
        sdk(ctx).organization.set_organization_member_role(
            user_id=user_id, role=role
        )
    )


@app.command("remove-member")
def remove_member(ctx: typer.Context, user_id: UserID) -> None:
    """Remove a member from the organization. Requires the admin role."""
    sdk(ctx).organization.remove_organization_member(user_id=user_id)
