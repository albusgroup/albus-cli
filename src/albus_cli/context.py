"""Global options shared by every command."""

from dataclasses import dataclass
from typing import cast

import typer
from albus_sdk import Albus

from albus_cli import client as transport


@dataclass(frozen=True)
class Options:
    base_url: str | None
    timeout: float


def options(ctx: typer.Context) -> Options:
    return cast(Options, ctx.obj)


def base_url(ctx: typer.Context) -> str:
    return transport.base_url(options(ctx).base_url)


def timeout(ctx: typer.Context) -> float:
    return options(ctx).timeout


def sdk(ctx: typer.Context) -> Albus:
    return transport.client(base_url(ctx), timeout(ctx))


def signed_in_sdk(ctx: typer.Context) -> Albus:
    """For the operations that accept only a human bearer token."""
    return transport.signed_in_client(base_url(ctx), timeout(ctx))


def public_sdk(ctx: typer.Context) -> Albus:
    """For the operations the API leaves unauthenticated."""
    return transport.public_client(base_url(ctx), timeout(ctx))
