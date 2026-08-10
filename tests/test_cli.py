import json
from pathlib import Path

import httpx
import pytest
from albus_sdk import errors
from typer.testing import CliRunner

from albus_cli.main import app, main
from tests.conftest import FakeAlbus

runner = CliRunner()


def test_run_builds_agent_config_from_flags(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app,
        [
            "sessions",
            "run",
            "s1",
            "-p",
            "hello",
            "--agent-name",
            "triage",
            "--model",
            "gemini-3.6-flash",
            "--provider",
            "gemini",
            "--credential",
            "albus.sh/secrets/key",
            "--tool",
            "WEB_SEARCH",
            "--max-steps",
            "5",
        ],
    )

    assert result.exit_code == 0, result.output
    call = albus.calls[0]
    assert call.name == "run_session"
    assert call.kwargs["id"] == "s1"
    assert call.kwargs["user_prompt"] == "hello"
    assert call.kwargs["wait"] is True
    agent = call.kwargs["agent"]
    assert agent.model.name == "gemini-3.6-flash"
    assert agent.model.provider is not None
    assert agent.model.provider.credential == "albus.sh/secrets/key"
    assert agent.tools == ["WEB_SEARCH"]
    assert agent.max_steps == 5
    output = json.loads(result.stdout)
    assert output["session"]["id"] == "s1"
    assert output["idempotency_key"] == "inv-1"


def test_waiting_run_disables_the_request_timeout(
    albus: FakeAlbus,
) -> None:
    args = [
        "sessions",
        "run",
        "s1",
        "-p",
        "hello",
        "--agent-name",
        "triage",
        "--model",
        "m",
    ]

    assert runner.invoke(app, args).exit_code == 0
    assert albus.init_kwargs[0]["client"].timeout.read is None

    assert runner.invoke(app, [*args, "--no-wait"]).exit_code == 0
    assert albus.init_kwargs[1]["client"].timeout.read == 30.0


def test_run_rejects_agent_file_combined_with_flags(
    albus: FakeAlbus, tmp_path: Path
) -> None:
    agent_file = tmp_path / "agent.json"
    agent_file.write_text('{"model": {"name": "m"}}')

    result = runner.invoke(
        app,
        [
            "sessions",
            "run",
            "s1",
            "-p",
            "hello",
            "--agent-name",
            "triage",
            "--model",
            "m",
            "--agent-file",
            str(agent_file),
        ],
    )

    assert result.exit_code == 2
    assert "--agent-file" in result.output
    assert albus.calls == []


def test_run_reads_agent_config_from_file(
    albus: FakeAlbus, tmp_path: Path
) -> None:
    agent_file = tmp_path / "agent.json"
    agent_file.write_text(
        '{"model": {"name": "m"}, "mcp_servers": '
        '[{"name": "github", "url": "https://mcp.example/mcp"}]}'
    )

    result = runner.invoke(
        app,
        [
            "sessions",
            "run",
            "s1",
            "-p",
            "hello",
            "--agent-name",
            "triage",
            "--agent-file",
            str(agent_file),
        ],
    )

    assert result.exit_code == 0, result.output
    agent = albus.calls[0].kwargs["agent"]
    assert agent.mcp_servers[0].name == "github"


def test_base_url_option_overrides_the_default_server(
    albus: FakeAlbus,
) -> None:
    result = runner.invoke(
        app,
        ["--base-url", "http://localhost:8080/api", "sessions", "list"],
    )

    assert result.exit_code == 0, result.output
    assert albus.init_kwargs[0]["server_url"] == "http://localhost:8080/api"


def test_secret_value_read_from_stdin(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app, ["secrets", "create", "gemini-key"], input="s3cret\n"
    )

    assert result.exit_code == 0, result.output
    assert albus.calls[0].kwargs["value"] == "s3cret"


def test_missing_api_key_reports_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ALBUS_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["albus", "sessions", "list"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "ALBUS_API_KEY is not set" in capsys.readouterr().err


def test_api_error_reports_status_and_message(
    albus: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**kwargs: object) -> None:
        raise errors.AlbusError(
            "session not found", httpx.Response(404, text="not found")
        )

    monkeypatch.setattr(albus.sessions, "list_sessions", fail)
    monkeypatch.setattr("sys.argv", ["albus", "sessions", "list"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "404: session not found" in capsys.readouterr().err
