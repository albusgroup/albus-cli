#!/bin/sh
# Install the Albus CLI (albus) from PyPI.
# Prefers uv, then pip --user, then pip inside a conda env.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/albusgroup/albus-cli/main/install.sh | sh
# Optional:
#   ALBUS_CLI_VERSION=0.1.0 curl -fsSL ... | sh

set -eu

PACKAGE="albus-cli"
VERSION="${ALBUS_CLI_VERSION:-}"

spec="$PACKAGE"
if [ -n "$VERSION" ]; then
    spec="${PACKAGE}==${VERSION}"
fi

say() {
    printf '%s\n' "$*"
}

err() {
    printf 'error: %s\n' "$*" >&2
}

have() {
    command -v "$1" >/dev/null 2>&1
}

pip_cmd() {
    if have python3; then
        if python3 -m pip --version >/dev/null 2>&1; then
            printf '%s\n' "python3 -m pip"
            return 0
        fi
    fi
    if have python; then
        if python -m pip --version >/dev/null 2>&1; then
            printf '%s\n' "python -m pip"
            return 0
        fi
    fi
    return 1
}

install_with_uv() {
    say "Installing ${spec} with uv tool install..."
    uv tool install "$spec"
    say "Installed with uv. Ensure the uv tool bin directory is on your PATH"
    say "(usually ~/.local/bin)."
}

install_with_pip() {
    cmd=$(pip_cmd) || return 1
    say "Installing ${spec} with ${cmd} --user..."
    # shellcheck disable=SC2086
    $cmd install --user "$spec"
    say "Installed with pip --user. Ensure your user scripts directory is on"
    say "PATH (often ~/.local/bin on Unix)."
}

install_with_conda() {
    have conda || return 1

    if [ -n "${CONDA_PREFIX:-}" ]; then
        env_python="${CONDA_PREFIX}/bin/python"
        env_label="$CONDA_PREFIX"
    else
        base_prefix=$(conda info --base 2>/dev/null) || return 1
        env_python="${base_prefix}/bin/python"
        env_label="$base_prefix"
    fi

    if [ ! -x "$env_python" ]; then
        err "conda found but Python is missing at ${env_python}"
        return 1
    fi

    if ! "$env_python" -m pip --version >/dev/null 2>&1; then
        say "pip missing in conda env; installing pip via conda..."
        conda install -y pip
    fi

    say "Installing ${spec} with pip into conda env (${env_label})..."
    "$env_python" -m pip install "$spec"
    say "Installed into the conda env. Activate that env (or ensure its"
    say "bin/Scripts directory is on PATH) to run albus."
}

if have uv; then
    install_with_uv
elif pip_cmd >/dev/null 2>&1; then
    install_with_pip
elif have conda; then
    install_with_conda
else
    err "need uv, pip, or conda on PATH"
    err "Install one of them, then re-run this script."
    exit 1
fi

if have albus; then
    say "Running: albus --help"
    albus --help
else
    say "albus is installed but not on PATH yet. Open a new shell or add"
    say "the scripts directory reported above to PATH, then run: albus --help"
fi

say "Set ALBUS_API_KEY before calling the API."
