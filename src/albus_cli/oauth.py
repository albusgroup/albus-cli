"""Auth0 sign-in: authorization code flow with PKCE over a loopback
redirect (RFC 8252). The CLI is a public native client, so there is no
client secret; the code verifier binds the code to this process.

Only LoginError leaves this module: every failure beneath it, transport
included, is translated into a message naming what failed and what the
caller can do about it."""

import base64
import hashlib
import os
import secrets
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

DOMAIN_ENV = "ALBUS_AUTH0_DOMAIN"
CLIENT_ID_ENV = "ALBUS_AUTH0_CLIENT_ID"
AUDIENCE_ENV = "ALBUS_AUTH0_AUDIENCE"

# Auth0 rejects a wildcard port in a callback URL, so every port the CLI
# may listen on is registered on the application and tried in order.
LOOPBACK_PORTS = (8484, 8485, 8486, 8487)
CALLBACK_PATH = "/callback"

# offline_access is what makes Auth0 issue a refresh token.
SCOPE = "openid profile email offline_access"

LOGIN_TIMEOUT = 180.0
CONNECTION_TIMEOUT = 5.0
TOKEN_TIMEOUT = 30.0


class LoginError(Exception):
    """Sign-in could not be completed."""


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_in: int


@dataclass(frozen=True)
class TenantConfig:
    domain: str
    client_id: str
    audience: str


# The "Albus CLI" native applications are public by design: a client id
# is an identifier, not a secret, and PKCE is what makes the exchange safe
# without one.
_DEV = TenantConfig(
    domain="dev-kbhnwdz2wrg6jl1a.us.auth0.com",
    client_id="v3VYSQpG7oVGIKVsuf4QITtIB8G2lFCX",
    audience="https://api.albus.dev",
)
_PRODUCTION = TenantConfig(
    domain="albusgroup.us.auth0.com",
    client_id="AKj5qYBdhejMt3ztROUJDBtHThmXmQL1",
    audience="https://api.albus.sh",
)
_UNCONFIGURED = TenantConfig(domain="", client_id="", audience="")
_TENANTS = {
    "http://localhost:8080/api": _DEV,
    "http://localhost:8080": _DEV,
    "https://albus.sh/api": _PRODUCTION,
}


def tenant_config(base_url: str) -> TenantConfig:
    """Resolve the Auth0 tenant serving an API base URL. Each field may
    be overridden from the environment for local development."""
    known = _TENANTS.get(base_url.rstrip("/").lower(), _UNCONFIGURED)
    tenant = TenantConfig(
        domain=os.environ.get(DOMAIN_ENV) or known.domain,
        client_id=os.environ.get(CLIENT_ID_ENV) or known.client_id,
        audience=os.environ.get(AUDIENCE_ENV) or known.audience,
    )

    unset = [
        env
        for env, value in (
            (DOMAIN_ENV, tenant.domain),
            (CLIENT_ID_ENV, tenant.client_id),
            (AUDIENCE_ENV, tenant.audience),
        )
        if not value
    ]
    if unset:
        raise LoginError(
            f"no Auth0 tenant configured for {base_url}: set " + ", ".join(unset)
        )

    return tenant


def authorize(
    tenant: TenantConfig,
    announce: Callable[[str], None],
    open_browser: bool = True,
) -> Tokens:
    """Sign in through the browser and exchange the code for tokens. The
    authorization URL is handed to `announce` so the caller, which owns
    output, can show it to a user whose browser did not open.

    `open_browser` false leaves opening it to the reader: a host with no
    browser, and an agent signing in the user sitting in front of one,
    both need the URL announced and nothing launched here — the loopback
    listener still waits, because the redirect comes back to it."""
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(32)
    redirect = _Redirect()
    listener = _listen(_redirect_handler(state, redirect))
    try:
        redirect_uri = f"http://127.0.0.1:{listener.server_port}{CALLBACK_PATH}"
        authorization = f"https://{tenant.domain}/authorize?" + urlencode(
            {
                "response_type": "code",
                "client_id": tenant.client_id,
                "redirect_uri": redirect_uri,
                "scope": SCOPE,
                "audience": tenant.audience,
                "code_challenge": _code_challenge(verifier),
                "code_challenge_method": "S256",
                "state": state,
            }
        )
        announce(authorization)
        if open_browser:
            webbrowser.open(authorization)

        _serve_redirect(listener, redirect)
    finally:
        listener.server_close()

    if redirect.failure:
        raise LoginError(redirect.failure)
    if not redirect.code:
        raise LoginError(_abandoned(redirect))

    return _tokens(
        tenant,
        {
            "grant_type": "authorization_code",
            "client_id": tenant.client_id,
            "code": redirect.code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        },
    )


def refresh(tenant: TenantConfig, refresh_token: str) -> Tokens:
    """Trade a refresh token for a fresh access token. Auth0 rotation
    may issue a new refresh token; when it does not, the returned
    refresh token is None and the caller keeps the one it has."""
    return _tokens(
        tenant,
        {
            "grant_type": "refresh_token",
            "client_id": tenant.client_id,
            "refresh_token": refresh_token,
        },
    )


@dataclass
class _Redirect:
    """What the browser delivered to the loopback listener."""

    code: str | None = None
    failure: str | None = None
    rejected: int = 0


def _abandoned(redirect: _Redirect) -> str:
    """Why the wait ended with nothing. Rejected requests are named:
    a stale tab from an earlier sign-in is the likely cause, and it
    looks nothing like an abandoned browser."""
    waited = f"no sign-in completed within {LOGIN_TIMEOUT:.0f} seconds"
    if not redirect.rejected:
        return waited

    return (
        f"{waited}; {redirect.rejected} redirect(s) carried another "
        "state and were rejected"
    )


def _listen(handler: type[BaseHTTPRequestHandler]) -> HTTPServer:
    refused: OSError | None = None
    for port in LOOPBACK_PORTS:
        try:
            return HTTPServer(("127.0.0.1", port), handler)
        except OSError as error:
            refused = error
            continue

    ports = ", ".join(str(port) for port in LOOPBACK_PORTS)
    raise LoginError(
        f"could not listen for the sign-in redirect on {ports}: {refused}"
    )


def _serve_redirect(listener: HTTPServer, redirect: _Redirect) -> None:
    """Serve requests until the browser delivers the redirect. A
    request the listener rejects does not end the wait, so a stray page
    cannot cancel a sign-in."""
    deadline = time.monotonic() + LOGIN_TIMEOUT
    while redirect.code is None and redirect.failure is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return

        listener.timeout = remaining
        listener.handle_request()


def _redirect_handler(
    state: str, redirect: _Redirect
) -> type[BaseHTTPRequestHandler]:
    class RedirectHandler(BaseHTTPRequestHandler):
        # Browsers open speculative connections that send no request. The
        # listener serves one connection at a time, so an unbounded read
        # would outlast the sign-in deadline.
        timeout = CONNECTION_TIMEOUT

        def do_GET(self) -> None:
            target = urlsplit(self.path)
            if target.path != CALLBACK_PATH:
                self._reply(HTTPStatus.NOT_FOUND, "Unknown path.")
                return

            query = parse_qs(target.query)
            if _query(query, "state") != state:
                redirect.rejected += 1
                self._reply(
                    HTTPStatus.BAD_REQUEST,
                    "This request did not come from albus login.",
                )
                return

            error = _query(query, "error")
            if error:
                description = _query(query, "error_description")
                redirect.failure = (
                    f"Auth0 rejected the sign-in: {description or error}"
                )
                self._reply(
                    HTTPStatus.BAD_REQUEST,
                    "Sign-in failed. Return to your terminal.",
                )
                return

            code = _query(query, "code")
            if not code:
                redirect.failure = "Auth0 redirect carried no code"
                self._reply(
                    HTTPStatus.BAD_REQUEST,
                    "Sign-in failed. Return to your terminal.",
                )
                return

            redirect.code = code
            self._reply(
                HTTPStatus.OK,
                "Signed in to Albus. You can close this tab.",
            )

        def _reply(self, status: HTTPStatus, message: str) -> None:
            page = (
                '<!doctype html><html><body style="font-family:'
                f' sans-serif"><p>{escape(message)}</p>'
                "</body></html>"
            ).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, format: str, *args: object) -> None:
            """Drop the default request log: the path holds the code."""

    return RedirectHandler


def _query(query: dict[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    return values[0] if values else None


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _token_client() -> httpx.Client:
    return httpx.Client(timeout=TOKEN_TIMEOUT)


def _tokens(tenant: TenantConfig, grant: dict[str, str]) -> Tokens:
    try:
        with _token_client() as client:
            response = client.post(
                f"https://{tenant.domain}/oauth/token", data=grant
            )
    except httpx.HTTPError as unreachable:
        raise LoginError(
            f"could not reach {tenant.domain}: {unreachable}"
        ) from None

    if response.status_code != HTTPStatus.OK:
        raise LoginError(f"Auth0 refused the grant: {_refusal(response)}")

    body = _body(tenant, response)
    rotated = body.get("refresh_token")
    return Tokens(
        access_token=_token_field(body, "access_token"),
        refresh_token=rotated if isinstance(rotated, str) else None,
        expires_in=_lifetime(body),
    )


def _body(tenant: TenantConfig, response: httpx.Response) -> dict[str, object]:
    try:
        decoded: dict[str, object] = response.json()
    except ValueError:
        raise LoginError(
            f"{tenant.domain} answered the token request with something "
            "other than JSON"
        ) from None

    return decoded


def _token_field(body: dict[str, object], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str):
        raise LoginError(f"Auth0 token response carried no {name}")

    return value


def _lifetime(body: dict[str, object]) -> int:
    value = body.get("expires_in")
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoginError("Auth0 token response carried no expires_in")

    return value


def _refusal(response: httpx.Response) -> str:
    try:
        body: dict[str, object] = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"

    described = body.get("error_description") or body.get("error")
    if isinstance(described, str):
        return described

    return f"HTTP {response.status_code}"
