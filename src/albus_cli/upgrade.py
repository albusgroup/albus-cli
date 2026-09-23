"""The upgrade notice: a line on stderr, after any command, when PyPI
has a newer albus-cli than the one running.

PyPI is asked at most once a day, with a short timeout, and the answer
is cached next to the credentials file — a missing answer too, so an
offline machine pays the timeout once a day and not once a command. A
failed lookup is silent: the command the reader ran already answered,
and this is not part of it.
"""

import json
import os
import tempfile
import time
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import httpx

from albus_cli import credentials, output

DISABLE_ENV = "ALBUS_NO_UPGRADE_CHECK"
PACKAGE = "albus-cli"
INDEX_URL = f"https://pypi.org/pypi/{PACKAGE}/json"
FILE_NAME = "upgrade-check.json"
INTERVAL_SECONDS = 24 * 60 * 60
TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class Check:
    """One attempt at PyPI: the version it named, or None when it did
    not answer, and when it was made."""

    latest: str | None
    checked_at: float


def notice() -> None:
    """Tell the reader a newer release exists, if one does."""
    if os.environ.get(DISABLE_ENV):
        return

    installed = version(PACKAGE)
    latest = _latest()
    if latest is None or not _newer(latest, installed):
        return

    output.upgrade_available(PACKAGE, installed, latest)


def path() -> Path:
    return credentials.path().parent / FILE_NAME


def _latest() -> str | None:
    """The newest version on PyPI: today's cached answer, or a fresh one."""
    cached = _cached()
    if cached is not None and time.time() - cached.checked_at < INTERVAL_SECONDS:
        return cached.latest

    fetched = fetch()
    _store(Check(fetched, time.time()))
    return fetched


def fetch() -> str | None:
    """Ask PyPI, and settle for no answer over a slow or failed one."""
    try:
        response = httpx.get(INDEX_URL, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        latest = response.json()["info"]["version"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None

    return latest if isinstance(latest, str) else None


def _cached() -> Check | None:
    try:
        document = json.loads(path().read_text())
    except (OSError, ValueError):
        return None

    if not isinstance(document, dict):
        return None

    latest = document.get("latest")
    checked_at = document.get("checked_at")
    if not isinstance(latest, str | None):
        return None

    if not isinstance(checked_at, int | float):
        return None

    return Check(latest, float(checked_at))


def _store(check: Check) -> None:
    target = path()
    document = {"latest": check.latest, "checked_at": check.checked_at}
    try:
        target.parent.mkdir(
            parents=True, exist_ok=True, mode=credentials.DIRECTORY_MODE
        )
        # Replaced whole, never rewritten in place: a command that reads
        # while another writes sees yesterday's answer or today's.
        descriptor, name = tempfile.mkstemp(
            dir=target.parent, prefix=f"{FILE_NAME}."
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w") as file:
                json.dump(document, file)

            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    except OSError:
        # An unwritable config directory is `main`'s error to report, and
        # only when a command needs it; a cache miss tomorrow is fine.
        return


def _newer(candidate: str, installed: str) -> bool:
    """Whether candidate is a later release than installed. Releases are
    plain dotted integers; anything else compares as not newer, so a
    pre-release or a local build is never nagged about."""
    try:
        return _release(candidate) > _release(installed)
    except ValueError:
        return False


def _release(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))
