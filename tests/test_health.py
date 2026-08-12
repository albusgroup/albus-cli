"""`albus health` is the first command the README has a reader run, and
`/health` has no `security` in `api/openapi.yaml`, so it must answer
before there is any credential to send."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from albus_cli import client, credentials
from albus_cli.main import app
from tests.conftest import FakeAlbus

runner = CliRunner()


def test_health_needs_no_credential(
    albus: FakeAlbus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(tmp_path / "empty"))
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)

    result = runner.invoke(app, ["health"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"status": "ok"}
    assert albus.init_kwargs[0]["access_token"] is None
    assert albus.init_kwargs[0]["api_key"] is None


def test_health_sends_no_api_key_either(albus: FakeAlbus) -> None:
    """The `albus` fixture exports an API key, which `/health` ignores."""
    assert runner.invoke(app, ["health"]).exit_code == 0
    assert albus.init_kwargs[0]["api_key"] is None


def test_rejected_health_names_no_credential(albus: FakeAlbus) -> None:
    """A 401 on a request that carried no credential must not send the
    reader to `albus login` over a credential it never sent."""
    runner.invoke(app, ["health"])

    assert "session" not in client.rejected()
    assert client.API_KEY_ENV in client.rejected()
