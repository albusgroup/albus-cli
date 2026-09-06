"""`albus memories groups` is how a reader discovers the group keys
`memories list --group` takes; both page with the cursor the server
returns."""

import json

from typer.testing import CliRunner

from albus_cli.main import app
from tests.conftest import FakeAlbus

runner = CliRunner()


def test_groups_lists_the_organizations_groups(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["memories", "groups"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "list_memory_groups"
    assert albus.calls[0].kwargs == {"after": None, "limit": 100}
    listed = json.loads(result.stdout)["memory_groups"][0]
    assert listed["key"] == "team-a"
    assert listed["active_memories"] == 2


def test_groups_pages_with_the_cursor(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app, ["memories", "groups", "--after", "c1", "--limit", "5"]
    )

    assert result.exit_code == 0, result.output
    assert albus.calls[0].kwargs == {"after": "c1", "limit": 5}


def test_list_names_the_group(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["memories", "list", "--group", "team-a"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "list_memories"
    assert albus.calls[0].kwargs == {
        "group": "team-a",
        "after": None,
        "limit": 100,
    }
    listed = json.loads(result.stdout)["memories"][0]
    assert listed["content"] == "prefers terse answers"


def test_list_requires_a_group(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["memories", "list"])

    assert result.exit_code != 0
    assert albus.calls == []


def test_delete_names_the_group_and_memory(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app, ["memories", "delete", "m1", "--group", "team-a"]
    )

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "delete_memory"
    assert albus.calls[0].kwargs == {"group": "team-a", "id": "m1"}
    assert result.stdout == ""


def test_delete_group(albus: FakeAlbus) -> None:
    result = runner.invoke(
        app, ["memories", "delete-group", "--group", "team-a"]
    )

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "delete_memory_group"
    assert albus.calls[0].kwargs == {"group": "team-a"}
