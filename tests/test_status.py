"""What `albus status` reports. It is the one command a coding agent runs
to learn where it stands, so its answer is JSON and its exit code says
nothing about whether the credential worked."""

import json
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from albus_sdk import errors, models
from typer.testing import CliRunner

from albus_cli import client, credentials
from albus_cli.credentials import Credential
from albus_cli.main import app
from tests.conftest import FakeAlbus

runner = CliRunner()

BASE_URL = "https://albus.sh/api"


@pytest.fixture(autouse=True)
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the credential store at tmp_path, and start signed out."""
    directory = tmp_path / "config"
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(directory))
    monkeypatch.delenv(credentials.XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)
    monkeypatch.delenv(client.BASE_URL_ENV, raising=False)
    return directory


def reported(*argv: str) -> dict[str, Any]:
    """`status`, with any global options ahead of it."""
    result = runner.invoke(app, [*argv, "status"])
    assert result.exit_code == 0, result.output
    parsed: dict[str, Any] = json.loads(result.output)
    return parsed


def signed_in() -> None:
    credentials.save(
        BASE_URL,
        Credential(
            access_token="stored-access",
            refresh_token="refresh",
            expires_at=time.time() + 86400,
        ),
    )


def test_no_credential_is_reported_rather_than_failed() -> None:
    """Nothing is stored and nothing is exported: the answer an agent
    needs is the report, so `status` succeeds and says so."""
    report = reported()

    assert report["credential"] == "none"
    assert report["authenticated"] is False
    assert report["base_url"] == BASE_URL
    assert report["cli_version"]
    assert "email" not in report


def test_a_stored_session_is_named_with_the_account_it_belongs_to(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)
    signed_in()

    report = reported()

    assert report["credential"] == "session"
    assert report["authenticated"] is True
    assert report["caller"] == {
        "user": {
            "user_id": "u1",
            "email": "carlo@albus.sh",
            "organizations": [{"id": "o1", "name": "Albus", "roles": ["owner"]}],
        }
    }
    assert albus.calls[-1].name == "whoami"


def test_an_api_key_wins_over_a_stored_session_and_names_the_key(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reporting the session's account would name a credential nothing
    will send: `/whoami` takes the key too, and names it."""
    signed_in()
    monkeypatch.setattr(albus.auth, "whoami", api_key_caller)

    report = reported()

    assert report["credential"] == "api_key"
    assert report["authenticated"] is True
    assert report["caller"] == {
        "api_key": {"name": "ci", "organization_id": "o1"}
    }
    assert albus.init_kwargs[0]["api_key"] == "test-key"


def api_key_caller(**kwargs: object) -> models.WhoamiResponse:
    """What `/whoami` answers an API key: the key and the organization it
    acts in, and no user."""
    return models.WhoamiResponse(
        api_key=models.AuthenticatedAPIKey(name="ci", organization_id="o1")
    )


def test_a_rejected_credential_is_the_answer_not_a_failure(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exiting non-zero when the news is bad would make the command an
    agent runs to find out where it stands unusable for that."""

    def unauthorized(**kwargs: object) -> None:
        raise errors.ErrUnauthorized(
            errors.ErrUnauthorizedData(message="unauthorized"),
            httpx.Response(401, text='{"message": "unauthorized"}'),
        )

    monkeypatch.setattr(albus.auth, "whoami", unauthorized)

    report = reported()

    assert report["credential"] == "api_key"
    assert report["authenticated"] is False
    assert "401" in report["error"]


def test_the_reported_api_is_the_one_the_command_would_call(
    albus: FakeAlbus,
) -> None:
    report = reported("--base-url", "http://localhost:8080/api")

    assert report["base_url"] == "http://localhost:8080/api"


def test_an_expired_session_that_cannot_be_renewed_is_reported(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session the store cannot renew is as much an answer to "where do
    I stand" as a server refusal, and reaches the caller the same way."""
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)
    credentials.save(
        BASE_URL,
        Credential(
            access_token="stale-access",
            refresh_token=None,
            expires_at=time.time() - 60,
        ),
    )

    report = reported()

    assert report["credential"] == "session"
    assert report["authenticated"] is False
    assert "expired" in report["error"]


def test_an_unreachable_api_is_reported(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(**kwargs: object) -> None:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(albus.auth, "whoami", unreachable)

    report = reported()

    assert report["authenticated"] is False
    assert "connection refused" in report["error"]
