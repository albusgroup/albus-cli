"""Credentials obtained by browser sign-in, stored on disk.

The file holds one entry per API base URL, so a credential for a dev
server and one for production cannot overwrite each other. Writes are
atomic under an exclusive lock: several processes may refresh at once,
and a half-written file would look like a broken login.
"""

import fcntl
import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR_ENV = "ALBUS_CONFIG_DIR"
XDG_CONFIG_HOME_ENV = "XDG_CONFIG_HOME"

FILE_NAME = "credentials.json"
VERSION = 1
FILE_MODE = 0o600
DIRECTORY_MODE = 0o700


class CorruptFile(Exception):
    """The file exists and this version cannot make sense of it."""

    def __init__(self, file: Path, reason: str) -> None:
        super().__init__(f"{file} is not a credentials file: {reason}")


@dataclass(frozen=True)
class Credential:
    access_token: str
    refresh_token: str | None
    # Unix epoch seconds, absolute so a stale file is detectable
    # without knowing when it was written.
    expires_at: float


def path() -> Path:
    """The credentials file the CLI reads first and always writes."""
    return _directory() / FILE_NAME


def load(base_url: str) -> Credential | None:
    """The stored credential for base_url, or None if there is none.

    A file or entry this version cannot read counts as "none": the
    caller then tells the user to sign in, which is the fix either way.
    Readers take no lock because every write lands by rename.
    """
    primary = path()
    file = primary if primary.exists() else _legacy_path()
    try:
        entries = _entries(file)
    except (OSError, CorruptFile):
        return None

    return _credential(entries.get(_key(base_url)))


def save(base_url: str, credential: Credential) -> None:
    _replace_entry(base_url, asdict(credential))


def delete(base_url: str) -> None:
    _replace_entry(base_url, None)


def renew(
    base_url: str, mint: Callable[[Credential], Credential]
) -> Credential | None:
    """Replace the stored credential with a freshly minted one, holding
    the lock across the minting.

    A refresh token is spendable once: under Auth0 rotation, a second
    process spending the same one is a reuse, and reuse detection
    revokes the whole family. So the read-modify-write covers the
    network call rather than only the write, and `mint` is handed the
    entry as it reads under the lock — already renewed by another
    process, most of the time, in which case returning it unchanged
    stores nothing and spends nothing.

    None means the entry is gone: a `logout` won the race, and the
    caller is signed out rather than holding a stale credential.
    """
    target = path()
    directory = target.parent
    directory.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
    directory.chmod(DIRECTORY_MODE)

    with _lock(directory):
        entries = _entries(target)
        current = _credential(entries.get(_key(base_url)))
        if current is None:
            return None

        minted = mint(current)
        if minted == current:
            return current

        entries[_key(base_url)] = asdict(minted)
        _write(target, {"version": VERSION, "credentials": entries})
        return minted


def _directory() -> Path:
    configured = os.environ.get(CONFIG_DIR_ENV)
    if configured:
        return Path(configured)

    xdg = os.environ.get(XDG_CONFIG_HOME_ENV)
    if xdg:
        return Path(xdg) / "albus"

    return Path.home() / ".config" / "albus"


def _legacy_path() -> Path:
    """Read-only fallback for the pre-XDG location."""
    return Path.home() / ".albus" / FILE_NAME


def _key(base_url: str) -> str:
    return base_url.rstrip("/")


def _replace_entry(base_url: str, entry: dict[str, object] | None) -> None:
    """Set or remove one entry, keeping every other entry intact.

    Raises rather than rewriting a file it could not read whole:
    replacing it would discard the entries it never saw.
    """
    target = path()
    if entry is None and not target.exists():
        return

    directory = target.parent
    directory.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
    directory.chmod(DIRECTORY_MODE)

    with _lock(directory):
        entries = _entries(target)
        if entry is None:
            entries.pop(_key(base_url), None)
        else:
            entries[_key(base_url)] = entry

        _write(target, {"version": VERSION, "credentials": entries})


@contextmanager
def _lock(directory: Path) -> Iterator[None]:
    """Serialize the read-modify-write across processes.

    The lock lives in its own file: the credentials file is replaced on
    every write, so a lock on it would not be seen by the next writer.
    """
    descriptor = os.open(
        directory / f"{FILE_NAME}.lock",
        os.O_CREAT | os.O_RDWR,
        FILE_MODE,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _write(target: Path, document: dict[str, object]) -> None:
    descriptor, name = tempfile.mkstemp(
        dir=target.parent, prefix=f"{FILE_NAME}."
    )
    temporary = Path(name)
    try:
        # mkstemp creates the file 0600, which is the mode we want.
        with os.fdopen(descriptor, "w") as file:
            file.write(json.dumps(document, indent=2) + "\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _entries(file: Path) -> dict[str, object]:
    """The stored entries, empty only when the file does not exist.

    Anything else that stops this version from reading the whole
    document raises, so the read-modify-write cannot replace entries it
    never saw. `load` is the caller that turns that into "no
    credential".
    """
    try:
        text = file.read_text()
    except FileNotFoundError:
        return {}
    except UnicodeDecodeError as error:
        raise CorruptFile(file, "not UTF-8 text") from error

    try:
        document = _mapping(json.loads(text))
    except json.JSONDecodeError as error:
        raise CorruptFile(file, f"invalid JSON: {error}") from error

    if document is None:
        raise CorruptFile(file, "not a JSON object")

    version = document.get("version")
    if version != VERSION:
        raise CorruptFile(file, f"version {version!r} is not {VERSION}")

    return _mapping(document.get("credentials")) or {}


def _credential(entry: object) -> Credential | None:
    fields = _mapping(entry)
    if fields is None:
        return None

    access_token = fields.get("access_token")
    refresh_token = fields.get("refresh_token")
    expires_at = fields.get("expires_at")
    if not isinstance(access_token, str):
        return None

    if refresh_token is not None and not isinstance(refresh_token, str):
        return None

    if not isinstance(expires_at, int | float):
        return None

    return Credential(access_token, refresh_token, float(expires_at))


def _mapping(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None

    return {str(key): item for key, item in value.items()}
