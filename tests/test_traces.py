"""`albus traces list` searches invocations; `traces get` reads one with
its spans and prints the body without the transport headers. Both follow
`next_cursor` to the end, or to `--limit`."""

import json
from datetime import UTC, datetime

from albus_sdk import models
from typer.testing import CliRunner

from albus_cli.main import app
from tests.conftest import FakeAlbus, span, trace, trace_response

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
        "limit": 100,
    }
    assert json.loads(result.stdout)["traces"][0]["invocation_key"] == "inv-1"


def test_list_follows_the_cursor_to_the_end(albus: FakeAlbus) -> None:
    albus.traces.trace_pages = {
        None: models.ListTracesResponse(
            traces=[trace("inv-3"), trace("inv-2")], next_cursor="c1"
        ),
        "c1": models.ListTracesResponse(traces=[trace("inv-1")]),
    }

    result = runner.invoke(app, ["traces", "list"])

    assert result.exit_code == 0, result.output
    assert [call.kwargs["after"] for call in albus.calls] == [None, "c1"]
    body = json.loads(result.stdout)
    assert [t["invocation_key"] for t in body["traces"]] == [
        "inv-3",
        "inv-2",
        "inv-1",
    ]
    assert "next_cursor" not in body


def test_list_stops_at_the_limit_and_keeps_the_cursor(
    albus: FakeAlbus,
) -> None:
    albus.traces.trace_pages = {
        None: models.ListTracesResponse(
            traces=[trace("inv-3"), trace("inv-2")], next_cursor="c1"
        ),
        "c1": models.ListTracesResponse(
            traces=[trace("inv-1")], next_cursor="c2"
        ),
    }

    result = runner.invoke(app, ["traces", "list", "--limit", "3"])

    assert result.exit_code == 0, result.output
    assert [call.kwargs["limit"] for call in albus.calls] == [3, 1]
    body = json.loads(result.stdout)
    assert len(body["traces"]) == 3
    assert body["next_cursor"] == "c2"


def test_list_rejects_a_limit_below_one(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["traces", "list", "--limit", "0"])

    assert result.exit_code == 2, result.output
    assert albus.calls == []


def test_list_passes_every_filter(albus: FakeAlbus) -> None:
    albus.traces.trace_pages = {
        "c1": models.ListTracesResponse(traces=[trace()])
    }

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
        "limit": 25,
    }
    body = json.loads(result.stdout)
    assert body["invocation_key"] == "inv-1"
    assert "headers" not in body


def test_get_collects_every_page_of_spans(albus: FakeAlbus) -> None:
    albus.traces.span_pages = {
        None: trace_response([span("a"), span("b")], next_cursor="c1"),
        "c1": trace_response([span("c")]),
    }

    result = runner.invoke(app, ["traces", "get", "inv-1", "--no-payloads"])

    assert result.exit_code == 0, result.output
    assert [call.kwargs["limit"] for call in albus.calls] == [500, 500]
    body = json.loads(result.stdout)
    assert [s["id"] for s in body["spans"]] == ["a", "b", "c"]
    assert "next_cursor" not in body


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


def test_get_asks_for_no_more_than_the_limit(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["traces", "get", "inv-1", "--limit", "5"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].kwargs["limit"] == 5


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
