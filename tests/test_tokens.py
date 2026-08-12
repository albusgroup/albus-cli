"""`albus tokens` maps each command to one SDK operation and prints the
response. `create` is the only one whose response carries the key value,
and the API returns it once, so the output is checked to hold it exactly
once and nothing else to print it again."""

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from albus_cli import client, credentials
from albus_cli.credentials import Credential
from albus_cli.main import app, main
from tests.conftest import FakeAlbus

runner = CliRunner()

BASE_URL = "https://albus.sh/api"


@pytest.fixture(autouse=True)
def signed_in(
    albus: FakeAlbus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> FakeAlbus:
    """A stored browser session, which is what `/tokens` accepts."""
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


def test_list_prints_the_tokens(signed_in: FakeAlbus) -> None:
    result = runner.invoke(app, ["tokens", "list"])

    assert result.exit_code == 0, result.output
    assert signed_in.calls[0].name == "list_tokens"
    assert json.loads(result.stdout)["tokens"][0]["id"] == "t1"


def test_create_prints_the_token_value_once(signed_in: FakeAlbus) -> None:
    result = runner.invoke(app, ["tokens", "create", "ci"])

    assert result.exit_code == 0, result.output
    call = signed_in.calls[0]
    assert call.name == "create_token"
    assert call.kwargs["name"] == "ci"
    assert json.loads(result.stdout)["token"] == "alb-t1-secret"
    assert result.output.count("alb-t1-secret") == 1


def test_get_prints_the_token_metadata(signed_in: FakeAlbus) -> None:
    result = runner.invoke(app, ["tokens", "get", "t1"])

    assert result.exit_code == 0, result.output
    call = signed_in.calls[0]
    assert call.name == "get_token"
    assert call.kwargs["id"] == "t1"
    assert json.loads(result.stdout)["name"] == "ci"


def test_delete_prints_nothing(signed_in: FakeAlbus) -> None:
    result = runner.invoke(app, ["tokens", "delete", "t1"])

    assert result.exit_code == 0, result.output
    call = signed_in.calls[0]
    assert call.name == "delete_token"
    assert call.kwargs["id"] == "t1"
    assert result.stdout == ""


def test_the_session_is_used_over_an_api_key(
    signed_in: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An API key is a 401 at `/tokens`, so precedence must not send it."""
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")

    assert runner.invoke(app, ["tokens", "list"]).exit_code == 0
    security = signed_in.init_kwargs[0]["security"]
    assert security.bearer_auth == "stored-access"
    assert security.api_key_auth is None


def test_only_an_api_key_asks_for_a_sign_in(
    albus: FakeAlbus,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(tmp_path / "empty"))
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")
    monkeypatch.setattr("sys.argv", ["albus", "tokens", "list"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "needs a browser session" in capsys.readouterr().err
    assert albus.calls == []
