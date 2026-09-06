"""`albus memories` — the memory groups agents share, and what they hold."""

from typing import Annotated

import typer

from albus_cli.context import sdk
from albus_cli.output import emit

app = typer.Typer(
    no_args_is_help=True, help="List and delete memory groups and memories."
)

Group = Annotated[
    str,
    typer.Option("--group", help="Memory group key."),
]
After = Annotated[
    str | None,
    typer.Option("--after", help="Pagination cursor from a previous page."),
]
Limit = Annotated[int, typer.Option("--limit", help="Page size.")]


@app.command("groups")
def list_groups(
    ctx: typer.Context, after: After = None, limit: Limit = 100
) -> None:
    """List the organization's memory groups."""
    emit(sdk(ctx).memories.list_memory_groups(after=after, limit=limit))


@app.command("list")
def list_memories(
    ctx: typer.Context, group: Group, after: After = None, limit: Limit = 100
) -> None:
    """List a group's memories, newest first."""
    emit(sdk(ctx).memories.list_memories(group=group, after=after, limit=limit))


@app.command("delete")
def delete(
    ctx: typer.Context,
    memory_id: Annotated[
        str, typer.Argument(metavar="ID", help="The memory ID.")
    ],
    group: Group,
) -> None:
    """Delete one memory of a group, permanently."""
    sdk(ctx).memories.delete_memory(group=group, id=memory_id)


@app.command("delete-group")
def delete_group(ctx: typer.Context, group: Group) -> None:
    """Delete every memory of a group."""
    sdk(ctx).memories.delete_memory_group(group=group)
