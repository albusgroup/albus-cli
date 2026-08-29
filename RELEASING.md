# Releasing the Albus CLI

A release runs the scripts below from a clean, up-to-date `master` checkout of
the private Albus repository — by a maintainer locally, or by the dispatched
release workflow described in
[Releasing from GitHub Actions](#releasing-from-github-actions). Either way they
run `./tools/check`, upload to PyPI or TestPyPI, push the released tree to the
public mirror as a single tagged commit, and close the mirror issues the release
fixes. Nothing publishes on push, on tag, or on merge.

## One-time PyPI setup

1. Create a PyPI account, verify email, enable 2FA, and save recovery codes.
2. Ask an owner to add you to the `albus-cli` project.
3. Create an API token limited to the `albus-cli` project and store it in a
   password manager.

TestPyPI has separate accounts and tokens.

Never put an API token in this repository, a command-line argument, shell
history, or a pull request.

## Choose a version

Use a normalized PEP 440 version, and bump `project.version` in
`pyproject.toml` in a reviewed pull request. Published versions cannot be
reused, so a release that has already shipped needs a new number rather than a
re-upload.

Bump the `albus-sdk==…` pin in the same pull request when the CLI needs a newer
SDK, and release that SDK version first: the pin must name a version that is on
PyPI, or the published CLI is uninstallable.

`tools/bump-sdk` makes that edit:

```bash
./tools/bump-sdk 0.11.0 0.2.0
```

It rewrites the pin and `project.version`, relocks, and checks that `uv.lock`
resolved the SDK version you named — which is also how an SDK release that did
not actually reach PyPI is caught. It leaves the edit uncommitted, because the
edit is a pull request. The release workflow runs the same script and opens
that pull request itself.

## Validate

From `clients/albus-cli/`, on the branch that carries the version bump:

```bash
./tools/check
./tools/publish --dry-run 0.2.0
```

The dry run applies every release guard — the version in `pyproject.toml`
agrees, the worktree is clean, `HEAD` is the commit pushed to its upstream —
then builds and prints the artifacts without uploading.

## Publish

Merge the version bump, then from a clean `master`:

```bash
read -s UV_PUBLISH_TOKEN
export UV_PUBLISH_TOKEN
./tools/publish 0.2.0
unset UV_PUBLISH_TOKEN
```

TestPyPI first, if the change is one you want to install before it is public:

```bash
./tools/publish --testpypi 0.2.0
```

A TestPyPI upload is a rehearsal. It does not update the mirror.

Verify:

```bash
uv tool install albus-cli==0.2.0
albus --help
```

## Releasing from GitHub Actions

A release running in GitHub Actions passes `--non-interactive`, which skips the
confirmation prompt because the dispatch already authorized the upload: a
maintainer with write access typed the version in and turned `dry_run` off.
The flag is refused when `GITHUB_ACTIONS` is unset: a phrase a script can type
is not a confirmation, so a local release keeps the prompt.
Deciding that from the environment is a guard against skipping the prompt out
of habit, not a boundary — `UV_PUBLISH_TOKEN` is what authorizes an upload, and
a maintainer holding it can already publish.

Actions checks out a detached `HEAD` with no upstream configured, so there the
publisher proves the same invariant against `GITHUB_REF` instead — the ref must
be a branch, `origin` must have it, and it must point at the commit being
released. Uploads still only run from `master`.

The CLI is published by its own dispatch, after the pull request that bumps the
`albus-sdk` pin and the CLI version has been reviewed and merged: the pin has
to name an SDK version that is already on PyPI. See
[`client-release-automation.md`](../../.agents/plans/client-release-automation.md).

## Copy the release to the public mirror

```bash
./tools/mirror-release --dry-run 0.2.0 /path/to/albus-cli
./tools/mirror-release 0.2.0 /path/to/albus-cli
```

`<mirror-checkout>` is your clone of `albusgroup/albus-cli`. The script
replaces its entire tree with this directory's, minus the files that only mean
something upstream, commits it as one `albus-cli <version>` commit carrying a
`Source-Commit` trailer, tags it `v<version>`, and pushes both atomically.

A fix for a user-reported bug names its report in the upstream commit message:

```text
Mirror-Issue: albusgroup/albus-cli#12
```

`mirror-release` reads those trailers between the previously released commit
and this one, and closes each issue with the version that carries the fix. A
reporter cannot see the private fix, so the release closing the issue is the
only signal they get.

A maintainer's own `git` and `gh` credentials do the push and the issue
closing; in Actions they come from the release workflow's token. Pushing
`.github/workflows/` to the mirror needs a credential allowed to write workflow
files.

The checkout you pass is only read: the release commit is built in a throwaway
clone of it, so a rejected push — the likely first-release outcome, since the
push needs that workflow scope — leaves nothing to unwind and the command is
simply run again. Pull the checkout afterwards to see the release in it.
