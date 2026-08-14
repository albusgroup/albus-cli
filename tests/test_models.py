"""`albus models list` is where a reader finds the name `sessions run
--model` takes, so it has to answer with the API key that a run uses
rather than the browser session `/tokens` needs."""

import json

from typer.testing import CliRunner

from albus_cli.main import app
from tests.conftest import FakeAlbus

runner = CliRunner()


def test_list_prints_the_models_and_providers(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "list_models"
    listed = json.loads(result.stdout)["models"][0]
    assert listed == {"name": "claude-opus-4-8", "provider": "anthropic"}


def test_list_uses_the_api_key(albus: FakeAlbus) -> None:
    assert runner.invoke(app, ["models", "list"]).exit_code == 0
    assert albus.init_kwargs[0]["api_key"] == "test-key"
