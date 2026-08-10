"""`albus agents` — inspect the agents that have run in the org."""

from typing import Annotated

import typer

from albus_cli.context import sdk
from albus_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="Inspect agents.")

AgentName = Annotated[
    str, typer.Argument(metavar="AGENT_NAME", help="Agent name.")
]


@app.command("list")
def list_agents(ctx: typer.Context) -> None:
    """List agents."""
    emit(sdk(ctx).agents.list_agents())


@app.command("get")
def get(ctx: typer.Context, name: AgentName) -> None:
    """Get an agent with its current revision."""
    emit(sdk(ctx).agents.get_agent(name=name))


@app.command("revision")
def revision(
    ctx: typer.Context,
    name: AgentName,
    revision: Annotated[
        str,
        typer.Argument(metavar="REVISION", help="Agent revision identifier."),
    ],
) -> None:
    """Get one revision of an agent."""
    emit(sdk(ctx).agents.get_agent_revision(name=name, revision=revision))
