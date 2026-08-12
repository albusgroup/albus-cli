# Contributing to albus-cli

Thanks for helping improve the Albus CLI.

## Report a problem

Open a [GitHub issue](https://github.com/albusgroup/albus-cli/issues) with:

- The installed `albus-cli` and Python versions.
- The command you ran and the exact output.
- The expected and actual behavior.

Do not include access tokens, organization keys, secret values, or other
sensitive data. `albus` never prints a credential; if you have pasted one into
a log, redact it and rotate the credential.

Report suspected vulnerabilities privately by following
[SECURITY.md](SECURITY.md), not by opening a public issue.

## This repository is a mirror

The CLI is developed in the private Albus repository, alongside the
`api/openapi.yaml` contract and the SDK it is built on, and each release is
copied here. This repository does not accept pull requests: a change merged
here is removed by the next release, so one opened here is commented on and
closed automatically.

Issues are the right channel, and they are read. Maintainers fix the problem
upstream, and the fix arrives in the next published version, which closes the
issue.

See [RELEASING.md](RELEASING.md) for how a version is produced and published.
