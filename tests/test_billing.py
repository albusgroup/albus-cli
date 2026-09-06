"""`albus billing` reads the balance and ledger with whichever credential
resolves; `checkout` is `bearerAuth`-only, so it must not send an API
key."""

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from albus_cli import credentials
from albus_cli.credentials import Credential
from albus_cli.main import app
from tests.conftest import FakeAlbus

runner = CliRunner()

BASE_URL = "https://albus.sh/api"


def test_balance(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["billing", "balance"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "get_credit_balance"
    assert json.loads(result.stdout)["balance_usd"] == "12.50"


def test_ledger_pages_with_the_cursor(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app, ["billing", "ledger", "--after", "c1", "--limit", "5"]
    )

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "list_credit_ledger"
    assert albus.calls[0].kwargs == {"after": "c1", "limit": 5}
    assert json.loads(result.stdout)["entries"][0]["kind"] == "purchase"


def test_checkout_uses_the_session_over_an_api_key(
    albus: FakeAlbus, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(tmp_path / "config"))
    monkeypatch.delenv(credentials.XDG_CONFIG_HOME_ENV, raising=False)
    credentials.save(
        BASE_URL,
        Credential(
            access_token="stored-access",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        ),
    )

    result = runner.invoke(
        app,
        [
            "billing",
            "checkout",
            "20",
            "--success-url",
            "https://example.com/ok",
            "--cancel-url",
            "https://example.com/back",
        ],
    )

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "create_checkout"
    assert albus.calls[0].kwargs == {
        "amount_usd": 20,
        "success_url": "https://example.com/ok",
        "cancel_url": "https://example.com/back",
    }
    assert albus.init_kwargs[0]["access_token"] == "stored-access"
    assert albus.init_kwargs[0]["api_key"] is None
    assert json.loads(result.stdout)["url"].startswith("https://")


def test_checkout_needs_both_urls(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["billing", "checkout", "20"])

    assert result.exit_code != 0
    assert albus.calls == []
