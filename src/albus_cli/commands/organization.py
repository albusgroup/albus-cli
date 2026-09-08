"""`albus organization` — the organization the commands act in, and its
members."""

from typing import Annotated, Literal

import typer

from albus_cli import client, credentials
from albus_cli.context import base_url, sdk, timeout
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


@app.command("use")
def use(
    ctx: typer.Context,
    organization_id: Annotated[
        str, typer.Argument(metavar="ORGANIZATION_ID", help="Organization ID.")
    ],
) -> None:
    """Persist the organization the browser session acts in."""
    if not organization_id:
        raise typer.BadParameter("ORGANIZATION_ID must not be empty.")

    _select(ctx, organization_id)


@app.command("default")
def default(ctx: typer.Context) -> None:
    """Use the earliest-joined organization by default."""
    _select(ctx, None)


def _select(ctx: typer.Context, organization_id: str | None) -> None:
    """Prove the membership with `/whoami`, then save it against the
    session that proved it."""
    api = base_url(ctx)
    selected = client.selection(api, timeout(ctx), organization_id)
    caller = selected.api.auth.whoami()
    credentials.set_organization(api, organization_id, selected.session)
    emit(caller)


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
