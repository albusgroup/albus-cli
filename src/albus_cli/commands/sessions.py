"""`albus sessions` — run and inspect agent sessions."""

from pathlib import Path
from typing import Annotated

import typer
from albus_sdk import models

# The SDK's models are pydantic's, so validating one raises pydantic's
# error; it arrives with `albus-sdk` rather than as a dependency of ours.
from pydantic import ValidationError

from albus_cli.client import client
from albus_cli.context import base_url, options, sdk
from albus_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="Run and inspect sessions.")

SessionID = Annotated[
    str,
    typer.Argument(
        metavar="SESSION_ID",
        help="Client-provided session identifier. Reuse it to continue "
        "the same session.",
    ),
]
After = Annotated[
    str | None,
    typer.Option("--after", help="Pagination cursor from a previous page."),
]
Limit = Annotated[int, typer.Option("--limit", help="Page size.")]


def agent_config(
    agent_file: Path | None,
    model: str | None,
    provider: str | None,
    credential: str | None,
    system_prompt: str | None,
    tools: list[str],
    max_steps: int | None,
) -> models.AgentConfig:
    if agent_file is not None:
        flags = (model, provider, credential, system_prompt, max_steps)
        if any(flag is not None for flag in flags) or tools:
            raise typer.BadParameter(
                "--agent-file holds the whole agent configuration and "
                "cannot be combined with the other agent options"
            )

        try:
            return models.AgentConfig.model_validate_json(agent_file.read_text())
        except ValidationError as invalid:
            raise typer.BadParameter(
                f"{agent_file} is not a valid agent configuration: "
                f"{_first(invalid)}"
            ) from invalid

    if model is None:
        raise typer.BadParameter(
            "--model is required unless --agent-file is given"
        )

    if (provider is None) != (credential is None):
        raise typer.BadParameter(
            "--provider and --credential must be given together"
        )

    provider_config = (
        models.Provider(name=provider, credential=credential)
        if provider is not None and credential is not None
        else None
    )

    return models.AgentConfig(
        model=models.Model(name=model, provider=provider_config),
        tools=tools or None,
        system_prompt=system_prompt,
        max_steps=max_steps,
    )


def _first(invalid: ValidationError) -> str:
    """The first thing wrong with a file the caller wrote, without
    pydantic's report of every field and its docs link."""
    error = invalid.errors()[0]
    where = ".".join(str(part) for part in error["loc"])
    if not where:
        return error["msg"]

    return f"{where}: {error['msg']}"


@app.command("run")
def run(
    ctx: typer.Context,
    session_id: SessionID,
    prompt: Annotated[
        str,
        typer.Option(
            "--prompt",
            "-p",
            help="The user prompt driving this invocation.",
        ),
    ],
    agent_name: Annotated[
        str,
        typer.Option(
            "--agent-name",
            help='Name identifying the agent (e.g. "support-triage").',
        ),
    ],
    model: Annotated[
        str | None,
        typer.Option(
            "--model", help='Model identifier (e.g. "gemini-3.6-flash").'
        ),
    ] = None,
    provider: Annotated[
        str | None,
        typer.Option("--provider", help='Provider name (e.g. "gemini").'),
    ] = None,
    credential: Annotated[
        str | None,
        typer.Option(
            "--credential",
            help="Secret reference the provider authenticates with "
            '(e.g. "albus.sh/secrets/my-key").',
        ),
    ] = None,
    system_prompt: Annotated[
        str | None,
        typer.Option(
            "--system-prompt", help="System instructions for the model."
        ),
    ] = None,
    tools: Annotated[
        list[str] | None,
        typer.Option(
            "--tool",
            help="Tool the model may call. Repeat to allow several.",
        ),
    ] = None,
    max_steps: Annotated[
        int | None,
        typer.Option(
            "--max-steps", help="Max model steps before the run stops."
        ),
    ] = None,
    agent_file: Annotated[
        Path | None,
        typer.Option(
            "--agent-file",
            exists=True,
            dir_okay=False,
            readable=True,
            help="JSON file holding the whole agent configuration, for "
            "configurations the flags do not cover (e.g. MCP servers).",
        ),
    ] = None,
    idempotency_key: Annotated[
        str | None,
        typer.Option(
            "--idempotency-key",
            help="Identifies this invocation so the call is retry-safe.",
        ),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option(
            "--wait/--no-wait",
            help="Block until the assistant response is available.",
        ),
    ] = True,
    wait_timeout: Annotated[
        int | None,
        typer.Option(
            "--wait-timeout",
            help="Seconds to block while waiting. Omit to wait indefinitely.",
        ),
    ] = None,
) -> None:
    """Run or resume a session."""
    agent = agent_config(
        agent_file,
        model,
        provider,
        credential,
        system_prompt,
        tools or [],
        max_steps,
    )
    timeout = options(ctx).timeout
    # A waiting run long-polls, so it outlives the request timeout.
    albus = client(base_url(ctx), None if wait else timeout)
    response = albus.sessions.run_session(
        id=session_id,
        user_prompt=prompt,
        agent_name=agent_name,
        agent=agent,
        idempotency_key=idempotency_key,
        # The server waits whenever the parameter is present, and 0 is
        # its unbounded wait.
        wait_timeout_seconds=(wait_timeout or 0) if wait else None,
    )
    result = response.result.model_dump(mode="json", exclude_none=True)
    # The server names the invocation's effective key in a header, and the
    # key the caller supplied is that value; a proxy that drops the header
    # is not a reason to lose the run's output.
    served = response.headers.get("idempotency-key", [])
    effective = served[0] if served else idempotency_key
    if effective is not None:
        result["idempotency_key"] = effective

    emit(result)


@app.command("list")
def list_sessions(ctx: typer.Context) -> None:
    """List all sessions."""
    emit(sdk(ctx).sessions.list_sessions())


@app.command("get")
def get(
    ctx: typer.Context,
    session_id: SessionID,
    after: After = None,
    limit: Limit = 100,
) -> None:
    """Get a session with a page of its messages."""
    emit(sdk(ctx).sessions.get_session(id=session_id, after=after, limit=limit))


@app.command("audit")
def audit(
    ctx: typer.Context,
    session_id: SessionID,
    after: After = None,
    limit: Limit = 100,
) -> None:
    """List a page of a session's audit log."""
    emit(
        sdk(ctx).sessions.get_session_audit(
            id=session_id, after=after, limit=limit
        )
    )


@app.command("delete")
def delete(ctx: typer.Context, session_id: SessionID) -> None:
    """Delete a session."""
    sdk(ctx).sessions.delete_session(id=session_id)
