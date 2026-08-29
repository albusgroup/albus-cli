"""Exercise the SDK bump against a fake `uv`.

The bump is the content of a release's pull request, so what matters is that
it edits exactly what it claims to and refuses when the lock disagrees.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"

FAKE_UV = """#!/usr/bin/env bash
case "$1" in
    lock) ;;
    export) echo "albus-sdk=={locked}" ;;
    *)
        echo "unexpected uv command: $1" >&2
        exit 1
        ;;
esac
"""

PYPROJECT = """[project]
name = "albus-cli"
version = "0.1.0"
dependencies = [
    # Pinned, not floated.
    "albus-sdk==0.9.0",
    "typer>=0.26.8,<0.28",
]
"""


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """A client root holding only what the bump reads."""
    tools = tmp_path / "tools"
    binaries = tmp_path / "bin"
    tools.mkdir()
    binaries.mkdir()

    shutil.copy(TOOLS / "bump-sdk", tools / "bump-sdk")
    (tools / "bump-sdk").chmod(0o755)
    uv = binaries / "uv"
    uv.write_text(FAKE_UV.format(locked="0.10.0"))
    uv.chmod(0o755)
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)

    return tmp_path


def bump(sandbox: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(sandbox / "tools/bump-sdk"), *arguments],
        capture_output=True,
        cwd=sandbox,
        encoding="utf8",
        env={"PATH": f"{sandbox / 'bin'}:/usr/bin:/bin"},
    )


def test_the_pin_and_the_version_move_together(sandbox: Path) -> None:
    result = bump(sandbox, "0.10.0", "0.2.0")

    assert result.returncode == 0, result.stderr
    pyproject = (sandbox / "pyproject.toml").read_text()
    assert 'version = "0.2.0"' in pyproject
    assert '"albus-sdk==0.10.0",' in pyproject
    assert "0.1.0 -> 0.2.0 on albus-sdk 0.10.0" in result.stdout


def test_the_comment_above_the_pin_survives(sandbox: Path) -> None:
    result = bump(sandbox, "0.10.0", "0.2.0")

    assert result.returncode == 0, result.stderr
    assert "# Pinned, not floated." in (sandbox / "pyproject.toml").read_text()


def test_republishing_the_current_version_is_refused(sandbox: Path) -> None:
    result = bump(sandbox, "0.10.0", "0.1.0")

    assert result.returncode == 1
    assert "already 0.1.0" in result.stderr


def test_a_lock_naming_another_sdk_version_fails(sandbox: Path) -> None:
    result = bump(sandbox, "0.11.0", "0.2.0")

    assert result.returncode == 1
    assert "uv.lock resolved albus-sdk 0.10.0" in result.stderr
