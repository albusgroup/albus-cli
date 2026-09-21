"""`albus memories` — the memory groups agents share, and what they hold."""

from typing import Annotated

import typer

from albus_cli import pagination
from albus_cli.context import sdk
from albus_cli.output import emit
from albus_cli.pagination import After, Limit

app = typer.Typer(
    no_args_is_help=True, help="List and delete memory groups and memories."
)

Group = Annotated[
    str,
    typer.Option("--group", help="Memory group key."),
]
# The most the API serves per request, from `api/openapi.yaml`.
PAGE = 1000


@app.command("groups")
def list_groups(
    ctx: typer.Context, after: After = None, limit: Limit = None
) -> None:
    """List the organization's memory groups."""
    memories = sdk(ctx).memories
    emit(
        pagination.collect(
            lambda cursor, size: memories.list_memory_groups(
                after=cursor, limit=size
            ),
            lambda page: page.memory_groups,
            PAGE,
            after,
            limit,
        )
    )


@app.command("list")
def list_memories(
    ctx: typer.Context, group: Group, after: After = None, limit: Limit = None
) -> None:
    """List a group's memories, newest first."""
    memories = sdk(ctx).memories
    emit(
        pagination.collect(
            lambda cursor, size: memories.list_memories(
                group=group, after=cursor, limit=size
            ),
            lambda page: page.memories,
            PAGE,
            after,
            limit,
        )
    )


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
