import json
from pathlib import Path

import httpx
import pytest
from albus_sdk import errors, models
from typer.testing import CliRunner

from albus_cli import client, credentials
from albus_cli.credentials import Credential
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
            "web_search",
            "--max-steps",
            "5",
        ],
    )

    assert result.exit_code == 0, result.output
    call = albus.calls[0]
    assert call.name == "run_session"
    assert call.kwargs["id"] == "s1"
    assert call.kwargs["user_prompt"] == "hello"
    assert call.kwargs["wait_timeout_seconds"] is None
    agent = call.kwargs["agent"]
    assert agent.model.name == "gemini-3.6-flash"
    assert agent.model.provider is not None
    assert agent.model.provider.credential == "albus.sh/secrets/key"
    assert agent.tools == models.Tools(web_search=models.WebSearchTool())
    assert agent.max_steps == 5
    output = json.loads(result.stdout)
    assert output["session"]["id"] == "s1"
    assert output["message"]["content"] == "hello back"
    assert output["invocation_key"] == "inv-1"


def test_an_invocation_that_has_not_answered_yet_carries_no_message(
    albus: FakeAlbus,
) -> None:
    """`--no-wait` returns as soon as the invocation is accepted, so there is no
    answer to print: an empty one would read as the agent's."""
    albus.sessions.message = None

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
            "--no-wait",
        ],
    )

    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["session"]["id"] == "s1"
    assert "message" not in output


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


def test_wait_flags_map_to_the_wait_timeout(albus: FakeAlbus) -> None:
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

    assert runner.invoke(app, [*args, "--no-wait"]).exit_code == 0
    assert albus.calls[0].kwargs["wait_timeout_seconds"] == 0

    assert runner.invoke(app, [*args, "--wait-timeout", "5"]).exit_code == 0
    assert albus.calls[1].kwargs["wait_timeout_seconds"] == 5


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


def sent_organization(albus: FakeAlbus) -> str | None:
    """The organization header the built transport adds to every
    request, or None when it sends none."""
    transport: httpx.Client = albus.init_kwargs[0]["client"]
    header: str | None = transport.headers.get(client.ORGANIZATION_HEADER)
    return header


def test_org_option_selects_the_organization_on_every_request(
    albus: FakeAlbus,
) -> None:
    result = runner.invoke(app, ["--org", "o2", "sessions", "list"])

    assert result.exit_code == 0, result.output
    assert sent_organization(albus) == "o2"


def test_org_is_read_from_the_environment(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(client.ORGANIZATION_ENV, "o3")

    result = runner.invoke(app, ["sessions", "list"])

    assert result.exit_code == 0, result.output
    assert sent_organization(albus) == "o3"


def test_without_an_org_the_server_picks_the_organization(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(client.ORGANIZATION_ENV, raising=False)

    result = runner.invoke(app, ["sessions", "list"])

    assert result.exit_code == 0, result.output
    assert sent_organization(albus) is None


def test_saved_org_selects_the_organization_for_a_browser_session(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(tmp_path / "config"))
    monkeypatch.delenv(credentials.XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)
    credentials.save(
        "https://api.albus.sh",
        Credential("access", "refresh", 1_800_000_000),
    )
    stored = credentials.session("https://api.albus.sh")
    assert stored is not None
    credentials.set_organization("https://api.albus.sh", "o2", stored)

    result = runner.invoke(
        app,
        ["--base-url", "https://api.albus.sh", "sessions", "list"],
    )

    assert result.exit_code == 0, result.output
    assert sent_organization(albus) == "o2"


def test_secret_value_read_from_stdin(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app, ["secrets", "create", "gemini-key"], input="s3cret\n"
    )

    assert result.exit_code == 0, result.output
    assert albus.calls[0].kwargs["value"] == "s3cret"


def test_invalid_agent_file_reports_the_first_problem(
    albus: FakeAlbus, tmp_path: Path
) -> None:
    agent_file = tmp_path / "agent.json"
    agent_file.write_text("nope")

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

    assert result.exit_code == 2
    # Rich wraps the message across the lines of its error panel.
    reported = " ".join(result.output.replace("│", "").split())
    assert "is not a valid agent configuration: Invalid JSON" in reported
    assert "Traceback" not in reported
    assert "pydantic.dev" not in reported
    assert albus.calls == []


def test_run_survives_a_missing_invocation_key_header(albus: FakeAlbus) -> None:
    """A proxy that strips the header must not cost the run's output."""
    albus.sessions.headers = {}
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
            "--invocation-key",
            "mine",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["invocation_key"] == "mine"


def test_unreachable_api_names_the_base_url(
    albus: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def refused(**kwargs: object) -> None:
        raise httpx.ConnectError("[Errno 111] Connection refused")

    monkeypatch.setattr(albus.sessions, "list_sessions", refused)
    monkeypatch.setattr(
        "sys.argv",
        ["albus", "--base-url", "http://localhost:9/api", "sessions", "list"],
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    reported = capsys.readouterr().err
    assert "could not reach http://localhost:9/api" in reported
    assert "Connection refused" in reported


def test_timeout_is_reported_as_one(
    albus: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def slow(**kwargs: object) -> None:
        raise httpx.ReadTimeout("")

    monkeypatch.setattr(albus.sessions, "list_sessions", slow)
    monkeypatch.setattr("sys.argv", ["albus", "sessions", "list"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "timed out" in capsys.readouterr().err


def test_undocumented_status_reports_the_status_not_the_body(
    albus: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A proxy answers HTML, and the SDK's fallback message carries the
    whole page."""

    def fail(**kwargs: object) -> None:
        raise errors.AlbusDefaultError(
            "API error occurred",
            httpx.Response(
                502,
                headers={"content-type": "text/html"},
                text="<html>bad gateway</html>",
            ),
        )

    monkeypatch.setattr(albus.sessions, "list_sessions", fail)
    monkeypatch.setattr("sys.argv", ["albus", "sessions", "list"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    reported = capsys.readouterr().err
    assert "502: bad gateway" in reported
    assert "<html>" not in reported


def test_unreadable_response_tells_the_reader_to_upgrade(
    albus: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**kwargs: object) -> None:
        raise errors.ResponseValidationError(
            "Response validation failed",
            httpx.Response(200, text="{}"),
            ValueError("sessions: field required"),
        )

    monkeypatch.setattr(albus.sessions, "list_sessions", fail)
    monkeypatch.setattr("sys.argv", ["albus", "sessions", "list"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    reported = capsys.readouterr().err
    assert "cannot read" in reported
    assert "upgrade" in reported.lower()


def test_rejected_api_key_names_the_variable(
    albus: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail(**kwargs: object) -> None:
        raise errors.AlbusError(
            "unauthorized", httpx.Response(401, text='{"message": "nope"}')
        )

    monkeypatch.setattr(albus.sessions, "list_sessions", fail)
    monkeypatch.setattr("sys.argv", ["albus", "sessions", "list"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "ALBUS_API_KEY" in capsys.readouterr().err


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


def test_cancel_names_the_session(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["sessions", "cancel", "my-session"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "cancel_session"
    assert albus.calls[0].kwargs == {"id": "my-session"}
    assert json.loads(result.stdout)["invocation_key"] == "inv-1"
