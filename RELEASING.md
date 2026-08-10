# Releasing the Albus CLI

Releases are intentionally manual during the MVP. The repository provides a
guarded publisher; it does not create commits, tags, or PyPI credentials.

## One-time PyPI setup

1. Create a PyPI account, verify email, enable 2FA, and save recovery codes.
2. Create the `albus-cli` project (first upload) or ask an owner to add you.
3. Create an API token limited to the `albus-cli` project and store it in a
   password manager.

TestPyPI has separate accounts and tokens.

Never put an API token in this repository, a command-line argument, shell
history, or a pull request.

## Choose a version

Use a normalized PEP 440 version. Bump `project.version` in `pyproject.toml`
and pin `albus-sdk` to the intended public SDK release before publishing.

Published versions cannot be reused.

## Prepare a release

1. Sync package sources from the private monorepo `cli/` if development
   happened there.
2. Update `version` and the `albus-sdk==…` pin in `pyproject.toml`.
3. Merge to `master` on a clean tree.
4. Validate:

   ```bash
   ./tools/publish --dry-run 0.1.0
   ```

## Publish

```bash
read -s UV_PUBLISH_TOKEN
export UV_PUBLISH_TOKEN
./tools/publish 0.1.0
unset UV_PUBLISH_TOKEN
```

TestPyPI:

```bash
./tools/publish --testpypi 0.1.0
```

Verify:

```bash
uv tool install albus-cli==0.1.0
albus --help
```

Or exercise the public installer after the release is visible on PyPI.
