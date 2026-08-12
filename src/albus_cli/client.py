"""Albus SDK client construction, and the credential it authenticates
with. Two credentials can authenticate a command: an API key from the
environment, and the browser session `albus login` stores on disk. This
module owns the choice between them, renewing the stored one, and every
sentence the CLI says about a credential — a message that names the
wrong credential sends an agent somewhere there is nothing to fix."""

import os
import time
from dataclasses import dataclass

import httpx
from albus_sdk import Albus, models
from albus_sdk.sdkconfiguration import SERVERS

from albus_cli import credentials, oauth
from albus_cli.credentials import Credential

API_KEY_ENV = "ALBUS_API_KEY"
BASE_URL_ENV = "ALBUS_BASE_URL"

# Renew slightly early: an access token that outlives the request it is
# sent on is not worth the 401.
EXPIRY_LEEWAY = 60.0


class NotSignedIn(Exception):
    """No credential this command can authenticate with."""


@dataclass(frozen=True)
class _Used:
    """The credential the last client was built with. A rejection is
    reported after the call, where the choice is no longer visible."""

    base_url: str
    api_key: bool


_used: _Used | None = None


def base_url(configured: str | None) -> str:
    """The API a command talks to, spelled as the credential store keys
    it. The SDK picks its first server when none is configured."""
    return configured or SERVERS[0]


def api_key() -> str | None:
    """The API key in the environment, which every command prefers to a
    stored session. It is read here so nothing else has to know the
    variable's name."""
    return os.environ.get(API_KEY_ENV)


def client(base_url: str, timeout: float | None) -> Albus:
    """Build an SDK client. A timeout of None disables the read timeout."""
    key = api_key()
    if key:
        # The environment wins over a stored session deliberately, so CI
        # and agent harnesses inject a credential without touching disk.
        return _client(
            base_url, timeout, models.Security(api_key_auth=key), True
        )

    stored = credentials.load(base_url)
    if stored is None:
        raise _signed_out(base_url)

    return bearer_client(base_url, timeout, _current(base_url, stored))


def signed_in_client(base_url: str, timeout: float | None) -> Albus:
    """A client on the browser session. The operations Albus accepts
    only a human bearer token for use it directly: an API key is a 401
    there, and the environment winning would be a 401 nobody asked
    for."""
    stored = credentials.load(base_url)
    if stored is None:
        raise NotSignedIn(
            f"not signed in to {base_url}. This command needs a browser "
            f"session, which {API_KEY_ENV} cannot stand in for: run "
            "`albus login`."
        )

    return bearer_client(base_url, timeout, _current(base_url, stored))


def public_client(base_url: str, timeout: float | None) -> Albus:
    """A client sending no credential, for an operation whose `security`
    in `api/openapi.yaml` is empty. `health` is the first command a
    reader runs, before there is a credential to demand.

    Nothing is recorded as used: a rejection here is not a credential's,
    and naming one would send the reader to sign in over a 401 no
    sign-in changes."""
    global _used
    _used = None
    return _built(base_url, timeout, models.Security())


def bearer_client(
    base_url: str, timeout: float | None, credential: Credential
) -> Albus:
    """A client on one credential, for `login` reading back the session
    it just stored rather than whatever precedence would pick."""
    return _client(
        base_url,
        timeout,
        models.Security(bearer_auth=credential.access_token),
        False,
    )


def credential(tokens: oauth.Tokens, replacing: Credential | None) -> Credential:
    """A storable credential for freshly issued tokens.

    Auth0 rotation may withhold a new refresh token, in which case the
    replaced credential's own one stays valid and is carried forward.
    `login` passes no `replacing`: an interactive sign-in may be a
    different account, whose access token must not be renewable with
    the previous account's refresh token.
    """
    keep = replacing.refresh_token if replacing else None
    return Credential(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token or keep,
        expires_at=time.time() + tokens.expires_in,
    )


def rejected() -> str:
    """What to do about a credential Albus refused, naming the one that
    was sent. Telling an API-key user to sign in is an instruction that
    leads nowhere, which is worse than none."""
    if _used is None:
        return (
            "the credential was rejected. Run `albus login`, or set "
            f"{API_KEY_ENV} to an Albus API key."
        )

    if _used.api_key:
        return (
            f"the API key in {API_KEY_ENV} was rejected by {_used.base_url}. "
            f"Check the key, or unset {API_KEY_ENV} and run `albus login`."
        )

    return f"your session for {_used.base_url} was rejected. Run `albus login`."


def unreachable(failure: Exception) -> str:
    """A request that never got an answer, named for where it was going:
    the reason alone — `[Errno 111] Connection refused`, or nothing at
    all for a timeout — does not say which URL is wrong or down."""
    reason = (
        "timed out"
        if isinstance(failure, httpx.TimeoutException)
        else str(failure)
    )
    return f"could not reach {_target()}: {reason}."


def unreadable() -> str:
    """A response this CLI cannot read: a body that does not match the
    API contract, or one that is not the JSON the operation returns. The
    two ways that happens are a CLI older than the API and something
    between them answering instead of Albus."""
    return (
        f"{_target()} returned a response this CLI cannot read. Upgrade "
        "with `uv tool upgrade albus-cli`, and check that the URL is Albus "
        "and not a proxy."
    )


def shadows_session() -> str | None:
    """What `login` adds when an API key will be used instead of the
    session it just stored. Silence would report an effect the next
    command does not have."""
    return _shadowing("unset it to use the account you just signed in as.")


def shadows_logout() -> str | None:
    """The same for `logout`: forgetting the session leaves an API key
    authenticating every command."""
    return _shadowing("commands stay authenticated until it is unset.")


def _signed_out(base_url: str) -> NotSignedIn:
    """Nothing stored to authenticate with, whether this command found
    no entry or a concurrent `logout` removed it."""
    return NotSignedIn(
        f"not signed in to {base_url}. Run `albus login`, or set "
        f"{API_KEY_ENV} to an Albus API key."
    )


def _target() -> str:
    """The API the last client was built for. A message about a request
    names it; one about a credential names the credential too."""
    if _used is None:
        return "the Albus API"

    return _used.base_url


def _shadowing(consequence: str) -> str | None:
    if not api_key():
        return None

    return f"{API_KEY_ENV} is set and takes precedence: {consequence}"


def _client(
    base_url: str,
    timeout: float | None,
    security: models.Security,
    api_key: bool,
) -> Albus:
    global _used
    _used = _Used(base_url=base_url, api_key=api_key)
    return _built(base_url, timeout, security)


def _built(
    base_url: str, timeout: float | None, security: models.Security
) -> Albus:
    return Albus(
        security=security,
        server_url=base_url,
        client=httpx.Client(follow_redirects=True, timeout=timeout),
    )


def _current(base_url: str, stored: Credential) -> Credential:
    """The stored credential, renewed if it is spent.

    Renewal runs inside the store's lock, so two processes starting from
    the same expired credential do not both spend its refresh token —
    under Auth0 rotation the second POST is a reuse, and reuse detection
    revokes the family, signing the user out of every machine.
    """
    if _fresh(stored):
        return stored

    _renewable(base_url, stored)
    tenant = oauth.tenant_config(base_url)
    renewed = credentials.renew(
        base_url, lambda current: _renewed(base_url, tenant, current)
    )
    if renewed is None:
        # A `logout` won the race for the entry while this one waited.
        raise _signed_out(base_url)

    return renewed


def _renewed(
    base_url: str, tenant: oauth.TenantConfig, current: Credential
) -> Credential:
    """The credential to store, given the entry read under the lock.
    Another process may have renewed it while this one waited, and its
    credential is returned untouched rather than spent a second time."""
    if _fresh(current):
        return current

    refresh_token = _renewable(base_url, current)
    try:
        tokens = oauth.refresh(tenant, refresh_token)
    except oauth.LoginError as rejected:
        raise NotSignedIn(
            f"your session for {base_url} expired and could not be "
            f"renewed ({rejected}). Run `albus login`."
        ) from None

    return credential(tokens, current)


def _renewable(base_url: str, spent: Credential) -> str:
    if spent.refresh_token is None:
        raise NotSignedIn(
            f"your session for {base_url} expired. Run `albus login`."
        )

    return spent.refresh_token


def _fresh(stored: Credential) -> bool:
    return time.time() < stored.expires_at - EXPIRY_LEEWAY
