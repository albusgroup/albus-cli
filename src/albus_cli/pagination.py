"""Following a paginated operation to its end. The API answers a list in
pages and names the next one in `next_cursor`; a reader at a terminal
wants the list, so a command collects the pages into the first one and
prints that. `--limit` caps how many items it collects, and the cursor
stays in the output only when the cap stopped it short — that is when
`--after` has somewhere to resume."""

from collections.abc import Callable
from typing import Annotated, Protocol, TypeVar

import typer

After = Annotated[
    str | None,
    typer.Option(
        "--after", help="Resume after this cursor from a `--limit` run."
    ),
]
Limit = Annotated[
    int | None,
    typer.Option(
        "--limit", min=1, help="Stop after this many; the default is all."
    ),
]


class Page(Protocol):
    next_cursor: str | None


P = TypeVar("P", bound=Page)
T = TypeVar("T")

Fetch = Callable[[str | None, int], P]
"""One request: the cursor to continue after, and the page size."""


def collect(
    fetch: Fetch[P],
    items: Callable[[P], list[T]],
    page_size: int,
    after: str | None,
    limit: int | None,
) -> P:
    """Every page from `after` on, merged into the first. `page_size` is
    the most the operation serves per request; `limit` is how many items
    the reader wants in all, or None for all of them."""
    first = fetch(after, size(page_size, limit))
    collected = items(first)
    cursor = first.next_cursor
    while cursor is not None and (limit is None or len(collected) < limit):
        remaining = None if limit is None else limit - len(collected)
        page = fetch(cursor, size(page_size, remaining))
        collected.extend(items(page))
        cursor = page.next_cursor

    first.next_cursor = cursor
    return first


def size(page_size: int, remaining: int | None) -> int:
    """How many to ask for: a full page, or what is left of the limit."""
    if remaining is None:
        return page_size

    return min(page_size, remaining)
