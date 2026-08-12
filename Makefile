.PHONY: install lint fmt typecheck test check

# uv owns the virtualenv. The albus-sdk version is pinned in pyproject.toml,
# so a sync installs what a release would publish against.
install:
	uv sync

lint: install
	uv run ruff check .
	uv run ruff format --check .

fmt: install
	uv run ruff format .

typecheck: install
	uv run mypy

test: install
	uv run pytest

check: lint typecheck test
