"""Exercise the publisher's guards with a sandboxed PATH.

The scripts are the release, so their refusals are behavior: each test runs
`tools/publish` against fake `git` and `uv` executables and asserts on which
guard fired.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"

FAKE_UV = """#!/usr/bin/env bash
case "$1" in
    build)
        mkdir -p dist
        : >dist/albus_cli-0.1.0-py3-none-any.whl
        : >dist/albus_cli-0.1.0.tar.gz
        ;;
    publish) echo "fake uv publish $*" ;;
esac
exit 0
"""

FAKE_GIT = """#!/usr/bin/env bash
case "$1" in
    status) ;;
    ls-remote) echo "0123456789abcdef refs/heads/master" ;;
    rev-parse) echo "{head_sha}" ;;
    symbolic-ref) ;;
    config) ;;
    *)
        echo "unexpected git command: $1" >&2
        exit 1
        ;;
esac
"""

PYPROJECT = """[project]
name = "albus-cli"
version = "0.1.0"
"""


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """A client root holding only what the publisher reads."""
    tools = tmp_path / "tools"
    binaries = tmp_path / "bin"
    tools.mkdir()
    binaries.mkdir()

    shutil.copy(TOOLS / "publish", tools / "publish")
    (tools / "publish").chmod(0o755)
    shutil.copy(TOOLS / "release_state.sh", tools / "release_state.sh")
    write_executable(tools / "check", "#!/usr/bin/env bash\nexit 0\n")
    write_executable(binaries / "uv", FAKE_UV)
    write_executable(
        binaries / "git", FAKE_GIT.format(head_sha="0123456789abcdef")
    )
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)

    return tmp_path


def publish(
    sandbox: Path,
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": f"{sandbox / 'bin'}:/usr/bin:/bin",
        "UV_PUBLISH_TOKEN": "fake-token",
    }
    environment.update(env or {})

    return subprocess.run(
        [str(sandbox / "tools/publish"), *arguments],
        capture_output=True,
        cwd=sandbox,
        encoding="utf8",
        env=environment,
    )


ACTIONS_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/master"}


def test_help_documents_the_non_interactive_flag(sandbox: Path) -> None:
    result = publish(sandbox, "--help")

    assert result.returncode == 0
    assert "--non-interactive" in result.stderr


def test_non_interactive_is_refused_outside_actions(sandbox: Path) -> None:
    result = publish(sandbox, "--non-interactive", "0.1.0")

    assert result.returncode == 1
    assert "--non-interactive is for GitHub Actions" in result.stderr


def test_uploads_without_a_prompt_in_actions(sandbox: Path) -> None:
    result = publish(sandbox, "--non-interactive", "0.1.0", env=ACTIONS_ENV)

    assert result.returncode == 0, result.stderr
    assert "Published albus-cli==0.1.0 to PyPI" in result.stdout


def test_actions_releases_run_from_a_branch(sandbox: Path) -> None:
    result = publish(
        sandbox,
        "--non-interactive",
        "0.1.0",
        env={**ACTIONS_ENV, "GITHUB_REF": "refs/tags/v0.1.0"},
    )

    assert result.returncode == 1
    assert "releases run from a branch" in result.stderr


def test_actions_releases_require_the_pushed_commit(sandbox: Path) -> None:
    write_executable(
        sandbox / "bin/git", FAKE_GIT.format(head_sha="deadbeefdeadbeef")
    )

    result = publish(sandbox, "--non-interactive", "0.1.0", env=ACTIONS_ENV)

    assert result.returncode == 1
    assert "HEAD is not the commit on origin/master" in result.stderr


def test_actions_uploads_stay_on_master(sandbox: Path) -> None:
    result = publish(
        sandbox,
        "--non-interactive",
        "0.1.0",
        env={**ACTIONS_ENV, "GITHUB_REF": "refs/heads/topic"},
    )

    assert result.returncode == 1
    assert "uploads must run from the master branch" in result.stderr


def test_a_prompt_is_still_required_without_the_flag(sandbox: Path) -> None:
    result = publish(sandbox, "0.1.0", env=ACTIONS_ENV)

    assert result.returncode == 1
    assert "requires an interactive confirmation" in result.stderr


def test_the_version_must_match_pyproject(sandbox: Path) -> None:
    result = publish(sandbox, "--non-interactive", "0.2.0", env=ACTIONS_ENV)

    assert result.returncode == 1
    assert "pyproject.toml version is 0.1.0" in result.stderr
