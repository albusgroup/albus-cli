# Releasing the Albus CLI

A release is a maintainer running the scripts below from a clean, up-to-date
`master` checkout of the private Albus repository: they run `./tools/check`,
upload to PyPI or TestPyPI, push the released tree to the public mirror as a
single tagged commit, and close the mirror issues the release fixes. Nothing
publishes from CI, on push, on tag, or on merge.

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

Your own `git` and `gh` credentials do the push and the issue closing; there is
no stored mirror token. Pushing `.github/workflows/` to the mirror needs a
credential with workflow scope.

The checkout you pass is only read: the release commit is built in a throwaway
clone of it, so a rejected push — the likely first-release outcome, since the
push needs that workflow scope — leaves nothing to unwind and the command is
simply run again. Pull the checkout afterwards to see the release in it.
