"""`albus traces list` searches invocations; `traces get` reads one with a
page of spans and prints the body without the transport headers."""

import json
from datetime import UTC, datetime

from typer.testing import CliRunner

from albus_cli.main import app
from tests.conftest import FakeAlbus

runner = CliRunner()


def test_list_sends_no_filter_by_default(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["traces", "list"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "list_traces"
    assert albus.calls[0].kwargs == {
        "agent_name": None,
        "agent_revision": None,
        "status": None,
        "session_id": None,
        "since": None,
        "until": None,
        "after": None,
        "limit": 10,
    }
    assert json.loads(result.stdout)["traces"][0]["invocation_key"] == "inv-1"


def test_list_passes_every_filter(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app,
        [
            "traces",
            "list",
            "--agent-name",
            "support-triage",
            "--agent-revision",
            "r1",
            "--status",
            "FAILED",
            "--session",
            "s1",
            "--since",
            "2026-01-01T00:00:00Z",
            "--after",
            "c1",
            "--limit",
            "3",
        ],
    )

    assert result.exit_code == 0, result.output
    kwargs = albus.calls[0].kwargs
    assert kwargs["agent_name"] == "support-triage"
    assert kwargs["agent_revision"] == "r1"
    assert kwargs["status"] == "FAILED"
    assert kwargs["session_id"] == "s1"
    assert kwargs["since"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert kwargs["after"] == "c1"
    assert kwargs["limit"] == 3


def test_list_rejects_an_unknown_status(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["traces", "list", "--status", "DONE"])

    assert result.exit_code != 0
    assert albus.calls == []


def test_get_defaults_to_final_attempt_with_payloads(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["traces", "get", "inv-1"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "get_trace"
    assert albus.calls[0].kwargs == {
        "invocation_key": "inv-1",
        "payloads": True,
        "attempts": "final",
        "after": None,
        "limit": None,
    }
    body = json.loads(result.stdout)
    assert body["invocation_key"] == "inv-1"
    assert "headers" not in body


def test_get_reads_the_shape_of_every_attempt(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app,
        [
            "traces",
            "get",
            "inv-1",
            "--no-payloads",
            "--attempts",
            "all",
            "--limit",
            "500",
        ],
    )

    assert result.exit_code == 0, result.output
    kwargs = albus.calls[0].kwargs
    assert kwargs["payloads"] is False
    assert kwargs["attempts"] == "all"
    assert kwargs["limit"] == 500


def test_list_accepts_an_offset_time(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app, ["traces", "list", "--since", "2026-01-01T02:00:00+02:00"]
    )

    assert result.exit_code == 0, result.output
    assert albus.calls[0].kwargs["since"] == datetime(2026, 1, 1, tzinfo=UTC)


def test_list_rejects_a_time_without_offset(albus: FakeAlbus) -> None:
    for value in ("2026-01-01T00:00:00", "2026-01-01", "yesterday"):
        result = runner.invoke(app, ["traces", "list", "--until", value])

        assert result.exit_code == 2, result.output
        assert "2026-01-01T00:00:00Z" in result.output
    assert albus.calls == []
