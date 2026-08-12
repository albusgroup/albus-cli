"""`albus invites create` maps to `createInvite`, sending the email alone
and leaving `role` and `organization_id` to the API: one user is one
organization for the beta. `/invites` is `bearerAuth`-only, so an API key
must not be sent."""

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from albus_cli import client, credentials
from albus_cli.credentials import Credential
from albus_cli.main import app
from tests.conftest import FakeAlbus

runner = CliRunner()

BASE_URL = "https://albus.sh/api"


@pytest.fixture(autouse=True)
def signed_in(
    albus: FakeAlbus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FakeAlbus:
    """A stored browser session, which is what `/invites` accepts."""
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(tmp_path / "config"))
    monkeypatch.delenv(credentials.XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)
    credentials.save(
        BASE_URL,
        Credential(
            access_token="stored-access",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        ),
    )
    return albus


def test_create_sends_only_the_email(signed_in: FakeAlbus) -> None:
    result = runner.invoke(app, ["invites", "create", "new@example.com"])

    assert result.exit_code == 0, result.output
    call = signed_in.calls[0]
    assert call.name == "create_invite"
    assert call.kwargs == {"email": "new@example.com"}
    assert json.loads(result.stdout)["id"] == "i1"


def test_the_session_is_used_over_an_api_key(
    signed_in: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An API key is a 401 at `/invites`, so precedence must not send it."""
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")

    result = runner.invoke(app, ["invites", "create", "new@example.com"])

    assert result.exit_code == 0, result.output
    assert signed_in.init_kwargs[0]["access_token"] == "stored-access"
    assert signed_in.init_kwargs[0]["api_key"] is None
