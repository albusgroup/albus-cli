"""`albus traces` — what agent invocations did: their model and tool calls."""

from datetime import datetime
from typing import Annotated, Literal

import typer

from albus_cli.context import sdk
from albus_cli.output import emit

app = typer.Typer(
    no_args_is_help=True, help="Search and read invocation traces."
)

Status = Literal["RUNNING", "SUCCEEDED", "FAILED", "CANCELED"]
Attempts = Literal["final", "all"]

After = Annotated[
    str | None,
    typer.Option("--after", help="Pagination cursor from a previous page."),
]


def parse_time(value: str) -> datetime:
    """An RFC 3339 timestamp: ISO 8601 with a UTC offset or `Z`."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise typer.BadParameter(
            "expected an RFC 3339 time, e.g. 2026-01-01T00:00:00Z"
        ) from None
    if parsed.tzinfo is None:
        raise typer.BadParameter(
            "a UTC offset or Z is required, e.g. 2026-01-01T00:00:00Z"
        )
    return parsed


@app.command("list")
def list_traces(
    ctx: typer.Context,
    agent_name: Annotated[
        str | None,
        typer.Option("--agent-name", help="Only invocations of this agent."),
    ] = None,
    agent_revision: Annotated[
        str | None,
        typer.Option(
            "--agent-revision", help="Only invocations of this revision."
        ),
    ] = None,
    status: Annotated[
        Status | None,
        typer.Option("--status", help="Only invocations that ended this way."),
    ] = None,
    session_id: Annotated[
        str | None,
        typer.Option("--session", help="Only invocations of this session."),
    ] = None,
    since: Annotated[
        datetime | None,
        typer.Option(
            "--since",
            parser=parse_time,
            help="Started at or after this RFC 3339 time.",
        ),
    ] = None,
    until: Annotated[
        datetime | None,
        typer.Option(
            "--until",
            parser=parse_time,
            help="Started before this RFC 3339 time.",
        ),
    ] = None,
    after: After = None,
    limit: Annotated[int, typer.Option("--limit", help="Page size.")] = 10,
) -> None:
    """Search invocations, newest first."""
    emit(
        sdk(ctx).traces.list_traces(
            agent_name=agent_name,
            agent_revision=agent_revision,
            status=status,
            session_id=session_id,
            since=since,
            until=until,
            after=after,
            limit=limit,
        )
    )


@app.command("get")
def get(
    ctx: typer.Context,
    invocation_key: Annotated[
        str,
        typer.Argument(metavar="INVOCATION_KEY", help="The invocation."),
    ],
    payloads: Annotated[
        bool,
        typer.Option(
            "--payloads/--no-payloads",
            help="Include what each span was given and produced.",
        ),
    ] = True,
    attempts: Annotated[
        Attempts,
        typer.Option(
            "--attempts", help="Spans of the final attempt only, or of all."
        ),
    ] = "final",
    after: After = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", help="Page size; the default fits the mode."),
    ] = None,
) -> None:
    """Get one invocation and a page of its spans."""
    emit(
        sdk(ctx)
        .traces.get_trace(
            invocation_key=invocation_key,
            payloads=payloads,
            attempts=attempts,
            after=after,
            limit=limit,
        )
        .result
    )
