#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "error: clients/albus-cli/setup.sh currently supports macOS with Homebrew" >&2
    exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
    echo "error: install Homebrew from https://brew.sh first" >&2
    exit 1
fi

brew install uv
uv python install 3.11
make install

echo "CLI development setup complete. Run: make check"
