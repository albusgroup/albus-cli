import json
from pathlib import Path

import httpx
import pytest

from albus_cli import credentials, upgrade
from albus_cli.main import main
from tests.conftest import FakeAlbus


@pytest.fixture
def config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv(upgrade.DISABLE_ENV)
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(upgrade, "version", lambda _: "0.12.0")
    return tmp_path


def pypi_serving(
    monkeypatch: pytest.MonkeyPatch, latest: str | None
) -> list[int]:
    fetches: list[int] = []

    def fetch() -> str | None:
        fetches.append(1)
        return latest

    monkeypatch.setattr(upgrade, "fetch", fetch)
    return fetches


def run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
    monkeypatch.setattr("sys.argv", ["albus", *argv])
    with pytest.raises(SystemExit) as exit_info:
        main()

    code = exit_info.value.code
    return code if isinstance(code, int) else 1


def test_a_newer_release_is_announced_on_stderr_after_the_answer(
    albus: FakeAlbus,
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pypi_serving(monkeypatch, "0.13.0")

    assert run(monkeypatch, "sessions", "list") == 0

    out, err = capsys.readouterr()
    assert json.loads(out)["sessions"][0]["id"] == "s1"
    assert "albus-cli 0.13.0 is available (installed 0.12.0)" in err
    assert "uv tool upgrade albus-cli" in err


def test_the_same_or_an_older_release_is_not_announced(
    albus: FakeAlbus,
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for latest in ("0.12.0", "0.11.9", "0.13.0rc1"):
        pypi_serving(monkeypatch, latest)
        upgrade.path().unlink(missing_ok=True)

        assert run(monkeypatch, "sessions", "list") == 0

        assert "available" not in capsys.readouterr().err


def test_the_answer_is_cached_for_a_day(
    albus: FakeAlbus,
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fetches = pypi_serving(monkeypatch, "0.13.0")

    run(monkeypatch, "sessions", "list")
    run(monkeypatch, "sessions", "list")

    assert len(fetches) == 1
    assert capsys.readouterr().err.count("0.13.0 is available") == 2

    stale = json.loads(upgrade.path().read_text())
    stale["checked_at"] -= upgrade.INTERVAL_SECONDS + 1
    upgrade.path().write_text(json.dumps(stale))
    run(monkeypatch, "sessions", "list")

    assert len(fetches) == 2


def test_a_failed_lookup_is_silent(
    albus: FakeAlbus,
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fetches = pypi_serving(monkeypatch, None)

    assert run(monkeypatch, "sessions", "list") == 0
    assert run(monkeypatch, "sessions", "list") == 0

    assert capsys.readouterr().err == ""
    # The miss is remembered too: an offline machine pays the timeout
    # once a day, not once a command.
    assert len(fetches) == 1
    assert json.loads(upgrade.path().read_text())["latest"] is None


def test_the_notice_follows_a_failed_command_too(
    albus: FakeAlbus,
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pypi_serving(monkeypatch, "0.13.0")
    monkeypatch.delenv("ALBUS_API_KEY")

    assert run(monkeypatch, "sessions", "list") == 1

    err = capsys.readouterr().err
    assert err.index("ALBUS_API_KEY") < err.index("0.13.0 is available")


def test_the_check_can_be_switched_off(
    albus: FakeAlbus,
    config_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fetches = pypi_serving(monkeypatch, "0.13.0")
    monkeypatch.setenv(upgrade.DISABLE_ENV, "1")

    run(monkeypatch, "sessions", "list")

    assert fetches == []
    assert "available" not in capsys.readouterr().err


def test_fetch_reads_the_version_pypi_serves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == upgrade.INDEX_URL
        return httpx.Response(200, json={"info": {"version": "0.13.0"}})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, timeout: httpx.Client(transport=transport).get(url),
    )

    assert upgrade.fetch() == "0.13.0"


def test_fetch_settles_for_no_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", refuse)

    assert upgrade.fetch() is None
