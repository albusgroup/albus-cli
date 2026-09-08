"""`albus organization` maps one command to each `/organization` operation
and accepts either credential, since the API does."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from albus_cli import client, credentials
from albus_cli.credentials import Credential
from albus_cli.main import app
from tests.conftest import FakeAlbus
from tests.test_cli import sent_organization

runner = CliRunner()

BASE_URL = "https://albus.sh/api"
SESSION = Credential("access", "refresh", 1_800_000_000)


@pytest.fixture(autouse=True)
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the store at tmp_path so the real ~/.config is untouched."""
    directory = tmp_path / "config"
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(directory))
    monkeypatch.delenv(credentials.XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return directory


@pytest.fixture
def signed_in(albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch) -> FakeAlbus:
    """The SDK fake behind a stored browser session, with no API key:
    `use` and `default` act on the session alone."""
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)
    credentials.save(BASE_URL, SESSION)
    return albus


def stored() -> credentials.Session:
    session = credentials.session(BASE_URL)
    assert session is not None
    return session


def test_get(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "get"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "get_organization"


def test_use_persists_a_membership(signed_in: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "use", "o2"])

    assert result.exit_code == 0, result.output
    assert signed_in.calls[0].name == "whoami"
    assert sent_organization(signed_in) == "o2"
    assert credentials.organization(BASE_URL) == "o2"


def test_use_needs_a_browser_session(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "use", "o2"])

    assert result.exit_code != 0
    assert albus.calls == []
    assert credentials.organization(BASE_URL) is None


def test_use_rejects_an_empty_id(signed_in: FakeAlbus) -> None:
    credentials.set_organization(BASE_URL, "o2", stored())

    result = runner.invoke(app, ["organization", "use", ""])

    assert result.exit_code != 0
    assert signed_in.calls == []
    assert credentials.organization(BASE_URL) == "o2"


def test_use_refuses_to_save_onto_a_session_that_replaced_the_one_it_checked(
    signed_in: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `login` landing between `/whoami` and the write is another
    account, whose session must not inherit this one's organization."""
    whoami = signed_in.auth.whoami

    def logged_in_meanwhile(**kwargs: object) -> object:
        credentials.save(BASE_URL, Credential("other", None, 1_800_000_000))
        return whoami(**kwargs)

    monkeypatch.setattr(signed_in.auth, "whoami", logged_in_meanwhile)

    result = runner.invoke(app, ["organization", "use", "o2"])

    assert isinstance(result.exception, credentials.SessionReplaced)
    assert credentials.organization(BASE_URL) is None


def test_default_clears_the_saved_membership(signed_in: FakeAlbus) -> None:
    credentials.set_organization(BASE_URL, "o2", stored())

    result = runner.invoke(app, ["organization", "default"])

    assert result.exit_code == 0, result.output
    assert sent_organization(signed_in) is None
    assert credentials.organization(BASE_URL) is None
    active = json.loads(result.stdout)["user"]["active_organization"]
    assert active["name"] == "Albus"


def test_default_keeps_the_saved_membership_when_the_request_fails(
    signed_in: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials.set_organization(BASE_URL, "o2", stored())

    def refused(**kwargs: object) -> None:
        raise ConnectionError("refused")

    monkeypatch.setattr(signed_in.auth, "whoami", refused)

    result = runner.invoke(app, ["organization", "default"])

    assert result.exit_code != 0
    assert credentials.organization(BASE_URL) == "o2"


def test_rename(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "rename", "Albus Labs"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "update_organization"
    assert albus.calls[0].kwargs == {"name": "Albus Labs"}


def test_members(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "members"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "list_organization_members"
    assert json.loads(result.stdout)["members"][0]["user_id"] == "u1"


def test_set_role(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "set-role", "u1", "member"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "set_organization_member_role"
    assert albus.calls[0].kwargs == {"user_id": "u1", "role": "member"}


def test_set_role_rejects_an_unknown_role(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "set-role", "u1", "owner"])

    assert result.exit_code != 0
    assert albus.calls == []


def test_remove_member_prints_nothing(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "remove-member", "u1"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "remove_organization_member"
    assert albus.calls[0].kwargs == {"user_id": "u1"}
    assert result.stdout == ""
