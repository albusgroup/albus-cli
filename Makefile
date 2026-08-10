.PHONY: install lint fmt typecheck test check

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
