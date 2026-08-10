"""Global options shared by every command."""

from dataclasses import dataclass
from typing import cast

import typer
from albus_sdk import Albus

from albus_cli.client import client


@dataclass(frozen=True)
class Options:
    base_url: str | None
    timeout: float


def options(ctx: typer.Context) -> Options:
    return cast(Options, ctx.obj)


def sdk(ctx: typer.Context) -> Albus:
    opts = options(ctx)
    return client(opts.base_url, opts.timeout)
