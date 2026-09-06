"""`albus billing` — the organization's prepaid credits.

`/billing/checkout` is `bearerAuth`-only: an API key cannot spend money, so
`checkout` takes the browser session with `signed_in_sdk`. Reading the
balance and the ledger accepts either credential.
"""

from typing import Annotated

import typer

from albus_cli.context import sdk, signed_in_sdk
from albus_cli.output import emit

app = typer.Typer(no_args_is_help=True, help="Read and top up prepaid credits.")

After = Annotated[
    str | None,
    typer.Option("--after", help="Pagination cursor from a previous page."),
]
Limit = Annotated[int, typer.Option("--limit", help="Page size.")]


@app.command("balance")
def balance(ctx: typer.Context) -> None:
    """Read the organization's credit balance in USD."""
    emit(sdk(ctx).billing.get_credit_balance())


@app.command("ledger")
def ledger(ctx: typer.Context, after: After = None, limit: Limit = 100) -> None:
    """List the credit ledger, newest first."""
    emit(sdk(ctx).billing.list_credit_ledger(after=after, limit=limit))


@app.command("checkout")
def checkout(
    ctx: typer.Context,
    amount_usd: Annotated[
        int,
        typer.Argument(
            metavar="AMOUNT_USD", help="Whole US dollars of credit to buy."
        ),
    ],
    success_url: Annotated[
        str,
        typer.Option(
            "--success-url",
            help="Where the payment page sends the buyer after paying.",
        ),
    ],
    cancel_url: Annotated[
        str,
        typer.Option(
            "--cancel-url",
            help="Where the payment page sends the buyer who backs out.",
        ),
    ],
) -> None:
    """Start a credit purchase and print the payment page URL."""
    emit(
        signed_in_sdk(ctx).billing.create_checkout(
            amount_usd=amount_usd,
            success_url=success_url,
            cancel_url=cancel_url,
        )
    )
