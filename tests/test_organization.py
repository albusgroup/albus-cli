"""`albus organization` maps one command to each `/organization` operation
and accepts either credential, since the API does."""

import json

from typer.testing import CliRunner

from albus_cli.main import app
from tests.conftest import FakeAlbus

runner = CliRunner()


def test_get(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "get"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "get_organization"
    assert json.loads(result.stdout)["name"] == "Albus"


def test_rename(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "rename", "Albus Labs"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "update_organization"
    assert albus.calls[0].kwargs == {"name": "Albus Labs"}


def test_members(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "members"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "list_organization_members"
    assert json.loads(result.stdout)["members"][0]["user_id"] == "u1"


def test_set_role(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "set-role", "u1", "member"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "set_organization_member_role"
    assert albus.calls[0].kwargs == {"user_id": "u1", "role": "member"}


def test_set_role_rejects_an_unknown_role(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "set-role", "u1", "owner"])

    assert result.exit_code != 0
    assert albus.calls == []


def test_remove_member_prints_nothing(albus: FakeAlbus) -> None:
    result = runner.invoke(app, ["organization", "remove-member", "u1"])

    assert result.exit_code == 0, result.output
    assert albus.calls[0].name == "remove_organization_member"
    assert albus.calls[0].kwargs == {"user_id": "u1"}
    assert result.stdout == ""
