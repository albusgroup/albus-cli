import json
import multiprocessing
import os
import stat
import time
from pathlib import Path

import pytest

from albus_cli import credentials
from albus_cli.credentials import Credential

BASE_URL = "https://albus.sh/api"


@pytest.fixture(autouse=True)
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the store at tmp_path so the real ~/.config is untouched."""
    directory = tmp_path / "config"
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(directory))
    monkeypatch.delenv(credentials.XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return directory


def credential(access_token: str = "access") -> Credential:
    return Credential(
        access_token=access_token,
        refresh_token="refresh",
        expires_at=1_800_000_000.0,
    )


def test_saved_credential_round_trips() -> None:
    credentials.save(BASE_URL, credential())

    assert credentials.load(BASE_URL) == credential()


def test_missing_file_has_no_credential() -> None:
    assert credentials.load(BASE_URL) is None


def test_config_dir_env_wins_over_xdg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    monkeypatch.setenv(credentials.XDG_CONFIG_HOME_ENV, str(tmp_path / "xdg"))

    assert credentials.path() == config_dir / "credentials.json"


def test_xdg_config_home_gets_an_albus_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(credentials.CONFIG_DIR_ENV)
    monkeypatch.setenv(credentials.XDG_CONFIG_HOME_ENV, str(tmp_path / "xdg"))

    assert credentials.path() == tmp_path / "xdg/albus/credentials.json"


def test_home_config_is_the_last_resort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(credentials.CONFIG_DIR_ENV)

    expected = tmp_path / "home/.config/albus/credentials.json"
    assert credentials.path() == expected


def test_legacy_file_is_read_when_the_primary_is_absent(
    tmp_path: Path,
) -> None:
    write_document(
        tmp_path / "home/.albus/credentials.json",
        {"version": 1, "credentials": {BASE_URL: entry("legacy")}},
    )

    loaded = credentials.load(BASE_URL)

    assert loaded is not None
    assert loaded.access_token == "legacy"


def test_legacy_file_is_never_written(tmp_path: Path) -> None:
    legacy = tmp_path / "home/.albus/credentials.json"
    write_document(
        legacy, {"version": 1, "credentials": {BASE_URL: entry("legacy")}}
    )

    credentials.save(BASE_URL, credential("fresh"))

    assert json.loads(legacy.read_text())["credentials"][BASE_URL] == entry(
        "legacy"
    )
    loaded = credentials.load(BASE_URL)
    assert loaded is not None
    assert loaded.access_token == "fresh"


def test_a_trailing_slash_is_the_same_entry() -> None:
    credentials.save(f"{BASE_URL}/", credential())

    assert credentials.load(BASE_URL) == credential()
    assert entries() == {BASE_URL: entry("access")}


def test_two_base_urls_do_not_collide() -> None:
    other = "http://localhost:8080"
    credentials.save(BASE_URL, credential("prod"))
    credentials.save(other, credential("dev"))

    for base_url, access_token in ((BASE_URL, "prod"), (other, "dev")):
        loaded = credentials.load(base_url)
        assert loaded is not None
        assert loaded.access_token == access_token


def test_delete_keeps_the_other_entries() -> None:
    other = "http://localhost:8080"
    credentials.save(BASE_URL, credential())
    credentials.save(other, credential("dev"))

    credentials.delete(BASE_URL)

    assert credentials.load(BASE_URL) is None
    assert credentials.load(other) is not None


def test_delete_without_a_file_writes_nothing() -> None:
    """Signing out must not be what creates the credentials file."""
    credentials.delete(BASE_URL)

    assert not credentials.path().exists()
    assert credentials.load(BASE_URL) is None


def test_file_and_directory_are_private(config_dir: Path) -> None:
    config_dir.mkdir(parents=True)
    config_dir.chmod(0o755)

    credentials.save(BASE_URL, credential())

    assert stat.S_IMODE(credentials.path().stat().st_mode) == 0o600
    assert stat.S_IMODE(config_dir.stat().st_mode) == 0o700


unreadable_documents = [
    pytest.param(b"{not json", id="invalid-json"),
    pytest.param(b"[]", id="not-an-object"),
    pytest.param(b"\xff\xfe\x00", id="not-utf8"),
    pytest.param(
        json.dumps({"version": 2, "credentials": {}}).encode(),
        id="unknown-version",
    ),
]


@pytest.mark.parametrize("document", unreadable_documents)
def test_an_unreadable_document_reads_as_no_credential(
    document: bytes,
) -> None:
    write_bytes(credentials.path(), document)

    assert credentials.load(BASE_URL) is None


@pytest.mark.parametrize("document", unreadable_documents)
def test_an_unreadable_document_is_never_rewritten(document: bytes) -> None:
    """Rewriting it would discard the entries it hides."""
    write_bytes(credentials.path(), document)

    with pytest.raises(credentials.CorruptFile):
        credentials.save(BASE_URL, credential())

    with pytest.raises(credentials.CorruptFile):
        credentials.delete(BASE_URL)

    assert credentials.path().read_bytes() == document


@pytest.mark.parametrize(
    "malformed",
    [
        {},
        {"access_token": 1, "refresh_token": None, "expires_at": 1.0},
        {"access_token": "a", "refresh_token": 1, "expires_at": 1.0},
        {"access_token": "a", "refresh_token": None, "expires_at": "soon"},
        "not-an-object",
    ],
)
def test_a_malformed_entry_reads_as_no_credential(
    malformed: object,
) -> None:
    write_document(
        credentials.path(),
        {"version": 1, "credentials": {BASE_URL: malformed}},
    )

    assert credentials.load(BASE_URL) is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_an_unreadable_file_reads_as_no_credential() -> None:
    credentials.save(BASE_URL, credential())
    credentials.path().chmod(0o000)

    try:
        assert credentials.load(BASE_URL) is None
    finally:
        credentials.path().chmod(0o600)


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_an_unreadable_file_is_not_overwritten() -> None:
    """Rewriting entries this process never read would lose them."""
    credentials.save("http://localhost:8080", credential("dev"))
    before = credentials.path().read_text()
    credentials.path().chmod(0o000)

    try:
        with pytest.raises(PermissionError):
            credentials.save(BASE_URL, credential())
    finally:
        credentials.path().chmod(0o600)

    assert credentials.path().read_text() == before


def save_in_child(config_dir: str, base_url: str, access_token: str) -> None:
    os.environ[credentials.CONFIG_DIR_ENV] = config_dir
    credentials.save(
        base_url,
        Credential(
            access_token=access_token,
            refresh_token="refresh",
            expires_at=1_800_000_000.0,
        ),
    )


def test_a_failed_write_leaves_the_previous_file_intact(
    monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    """The new document reaches the target only by rename."""

    def refuse(source: object, destination: object) -> None:
        raise OSError("no space left on device")

    credentials.save(BASE_URL, credential())
    before = credentials.path().read_bytes()
    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(OSError):
        credentials.save("http://localhost:8080", credential("dev"))

    assert credentials.path().read_bytes() == before
    assert list(config_dir.glob(f"{credentials.FILE_NAME}.*")) == [
        config_dir / f"{credentials.FILE_NAME}.lock"
    ]


def test_a_writer_waits_for_the_lock(config_dir: Path) -> None:
    """A second writer blocks instead of overwriting a stale read."""
    credentials.save(BASE_URL, credential())
    child = multiprocessing.get_context("spawn").Process(
        target=save_in_child,
        args=(str(config_dir), "http://localhost:8080", "dev"),
    )

    with credentials._lock(config_dir):
        child.start()
        child.join(timeout=2)
        assert child.exitcode is None, "writer did not wait for the lock"

    child.join(timeout=30)
    assert child.exitcode == 0
    assert set(entries()) == {BASE_URL, "http://localhost:8080"}


def save_repeatedly(config_dir: str, base_url: str, count: int) -> None:
    for index in range(count):
        save_in_child(config_dir, base_url, f"access-{index}")


def test_concurrent_writers_lose_no_entries(config_dir: Path) -> None:
    context = multiprocessing.get_context("spawn")
    writers = [
        context.Process(
            target=save_repeatedly,
            args=(str(config_dir), f"https://albus.test/{index}", 20),
        )
        for index in range(4)
    ]

    for writer in writers:
        writer.start()

    for writer in writers:
        writer.join(timeout=120)
        assert writer.exitcode == 0

    assert set(entries()) == {
        f"https://albus.test/{index}" for index in range(4)
    }
    for index in range(4):
        loaded = credentials.load(f"https://albus.test/{index}")
        assert loaded is not None
        assert loaded.access_token == "access-19"


def store_under_lock(config_dir: str, access_token: str, hold: float) -> None:
    """Renew the entry the way another process would: under the lock,
    and slowly enough that a caller must wait to see the result."""
    os.environ[credentials.CONFIG_DIR_ENV] = config_dir
    target = Path(config_dir) / credentials.FILE_NAME
    with credentials._lock(Path(config_dir)):
        (Path(config_dir) / "holding").touch()
        time.sleep(hold)
        entries = credentials._entries(target)
        entries[BASE_URL] = entry(access_token)
        credentials._write(
            target, {"version": credentials.VERSION, "credentials": entries}
        )


def test_renew_mints_from_the_entry_read_under_the_lock(
    config_dir: Path,
) -> None:
    """A refresh token is spendable once, so the minting waits for the
    lock and starts from what the winner stored, not from the stale
    credential the caller came in with."""
    credentials.save(BASE_URL, credential())
    child = multiprocessing.get_context("spawn").Process(
        target=store_under_lock, args=(str(config_dir), "by-another", 2.0)
    )
    child.start()
    while not (config_dir / "holding").exists():
        time.sleep(0.05)

    # The child holds the lock and has not written yet, so a renewal
    # that read outside the lock would mint from the stale credential.
    minted_from: list[str] = []

    def mint(current: Credential) -> Credential:
        minted_from.append(current.access_token)
        return credential("renewed")

    renewed = credentials.renew(BASE_URL, mint)

    child.join(timeout=30)
    assert child.exitcode == 0
    assert minted_from == ["by-another"]
    assert renewed == credential("renewed")
    assert credentials.load(BASE_URL) == credential("renewed")


def test_renew_writes_nothing_when_the_entry_is_already_current() -> None:
    credentials.save(BASE_URL, credential())
    before = credentials.path().read_bytes()

    assert credentials.renew(BASE_URL, lambda current: current) == credential()
    assert credentials.path().read_bytes() == before


def test_renew_reports_an_entry_that_is_gone() -> None:
    """`logout` may win the race; the caller is signed out, not holding
    a credential it renewed after the user asked to forget it."""
    assert credentials.renew(BASE_URL, lambda current: credential()) is None


def entry(access_token: str) -> dict[str, object]:
    return {
        "access_token": access_token,
        "refresh_token": "refresh",
        "expires_at": 1_800_000_000.0,
    }


def entries() -> dict[str, object]:
    document = json.loads(credentials.path().read_text())
    credential_entries: dict[str, object] = document["credentials"]
    return credential_entries


def write_bytes(file: Path, content: bytes) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)


def write_document(file: Path, document: dict[str, object]) -> None:
    write_bytes(file, json.dumps(document).encode())
