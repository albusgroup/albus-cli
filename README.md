# albus CLI

Command-line client for the Albus REST API. Thin shell over the public
[`albus-sdk`](https://pypi.org/project/albus-sdk/) Python package: every
command maps to one API operation and prints JSON (pipe into `jq`).

## Install

macOS / Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/albusgroup/albus-cli/master/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/albusgroup/albus-cli/master/install.ps1 | iex
```

Pin a version:

```bash
ALBUS_CLI_VERSION=0.1.0 curl -fsSL https://raw.githubusercontent.com/albusgroup/albus-cli/master/install.sh | sh
```

The installer uses, in order: `uv tool install`, `pip install --user`, or
`pip` inside a conda environment. It does not download OS-specific Albus
binaries and does not check OS versions.

You can also install directly:

```bash
uv tool install albus-cli
# or
pip install --user albus-cli
```

## Authentication

```bash
export ALBUS_API_KEY=...     # organization API key
export ALBUS_BASE_URL=...    # optional; defaults to production
```

`--base-url` overrides `ALBUS_BASE_URL`, and `--timeout` bounds each request
(a waiting `sessions run` long-polls and is exempt).

The API key is the only credential, so the CLI covers only the operations that
accept `apiKeyAuth`.

## Commands

```bash
albus health

albus sessions run my-session -p "summarize the incident" \
  --agent-name support-triage --model gemini-3.6-flash \
  --provider gemini --credential albus.sh/secrets/gemini-key
albus sessions list
albus sessions get my-session --limit 20
albus sessions audit my-session --after "$cursor"
albus sessions delete my-session

albus secrets list
albus secrets create gemini-key --value ...
albus secrets get gemini-key
albus secrets update gemini-key < value.txt
albus secrets delete gemini-key

albus agents list
albus agents get support-triage
albus agents revision support-triage "$revision"
```

## Development

```bash
make install
make check      # ruff, mypy --strict, pytest
```

See [RELEASING.md](RELEASING.md) to publish a PyPI version.
