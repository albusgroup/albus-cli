"""Auth0 sign-in flow: the token endpoint is stubbed with an httpx mock
transport, and the loopback listener is driven over real loopback by a
thread standing in for the browser."""

import base64
import hashlib
import socket
import threading
import webbrowser
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import httpx
import pytest

from albus_cli import oauth

TENANT = oauth.TenantConfig(
    domain="dev.us.auth0.com",
    client_id="client-1",
    audience="https://api.albus.dev",
)
GRANTED = {
    "access_token": "access-1",
    "refresh_token": "refresh-1",
    "expires_in": 86400,
    "token_type": "Bearer",
}


def signed_in(state: str) -> list[dict[str, str]]:
    return [{"code": "code-1", "state": state}]


@dataclass
class Auth0:
    """Stubbed Auth0: answers the token endpoint and, in place of a
    browser, visits the loopback listener with the queries `redirect`
    produces for the state it was sent."""

    reply: httpx.Response
    redirect: Callable[[str], list[dict[str, str]]] = signed_in
    authorization: dict[str, str] = field(default_factory=dict)
    grant: dict[str, str] = field(default_factory=dict)
    pages: list[httpx.Response] = field(default_factory=list)
    announced: list[str] = field(default_factory=list)
    browser: threading.Thread | None = None

    def open(self, url: str) -> bool:
        self.authorization = _single(httpx.URL(url).params)
        self.browser = threading.Thread(target=self._visit)
        self.browser.start()
        return True

    def _visit(self) -> None:
        uri = self.authorization["redirect_uri"]
        for query in self.redirect(self.authorization["state"]):
            self.pages.append(httpx.get(uri, params=query))

    def token(self, request: httpx.Request) -> httpx.Response:
        self.grant = _single(httpx.QueryParams(request.content.decode()))
        return self.reply

    def wait(self) -> None:
        if self.browser:
            self.browser.join(timeout=5.0)


def sign_in(auth0: Auth0) -> oauth.Tokens:
    return oauth.authorize(TENANT, auth0.announced.append)


def _single(params: httpx.QueryParams) -> dict[str, str]:
    return {name: params[name] for name in params}


@pytest.fixture
def auth0(monkeypatch: pytest.MonkeyPatch) -> Iterator[Auth0]:
    stub = Auth0(reply=httpx.Response(200, json=GRANTED))
    transport = httpx.MockTransport(stub.token)
    monkeypatch.setattr(
        oauth, "_token_client", lambda: httpx.Client(transport=transport)
    )
    monkeypatch.setattr(webbrowser, "open", stub.open)
    yield stub
    stub.wait()


def test_authorize_exchanges_the_redirected_code_for_tokens(
    auth0: Auth0, capsys: pytest.CaptureFixture[str]
) -> None:
    tokens = sign_in(auth0)

    assert tokens == oauth.Tokens(
        access_token="access-1",
        refresh_token="refresh-1",
        expires_in=86400,
    )

    authorization = auth0.authorization
    assert authorization["response_type"] == "code"
    assert authorization["client_id"] == "client-1"
    assert authorization["audience"] == TENANT.audience
    assert authorization["scope"] == oauth.SCOPE
    assert authorization["code_challenge_method"] == "S256"
    assert authorization["redirect_uri"].startswith("http://127.0.0.1:")
    assert authorization["redirect_uri"].endswith("/callback")

    verifier = auth0.grant["code_verifier"]
    assert 43 <= len(verifier) <= 128
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    assert authorization["code_challenge"] == challenge

    assert auth0.grant["grant_type"] == "authorization_code"
    assert auth0.grant["code"] == "code-1"
    assert auth0.grant["redirect_uri"] == authorization["redirect_uri"]
    assert "client_secret" not in auth0.grant

    auth0.wait()
    assert "close this tab" in auth0.pages[0].text

    announced = auth0.announced[0]
    assert announced.startswith(f"https://{TENANT.domain}/authorize?")
    assert verifier not in announced
    assert "code-1" not in announced
    assert capsys.readouterr().out == ""


def test_authorize_rejects_a_redirect_carrying_another_state(
    auth0: Auth0,
) -> None:
    auth0.redirect = lambda state: [
        {"code": "forged", "state": "not-the-state"},
        {"code": "code-1", "state": state},
    ]

    tokens = sign_in(auth0)

    assert tokens.access_token == "access-1"
    assert auth0.grant["code"] == "code-1"
    auth0.wait()
    assert auth0.pages[0].status_code == 400
    assert "did not come from albus login" in auth0.pages[0].text


def test_authorize_reports_an_auth0_error_redirect(auth0: Auth0) -> None:
    auth0.redirect = lambda state: [
        {
            "error": "access_denied",
            "error_description": "user cancelled",
            "state": state,
        }
    ]

    with pytest.raises(oauth.LoginError, match="user cancelled"):
        sign_in(auth0)

    assert auth0.grant == {}


def test_authorize_reports_a_redirect_without_a_code(
    auth0: Auth0,
) -> None:
    auth0.redirect = lambda state: [{"state": state}]

    with pytest.raises(oauth.LoginError, match="carried no code"):
        sign_in(auth0)


def test_authorize_reports_a_refused_code_exchange(auth0: Auth0) -> None:
    auth0.reply = httpx.Response(
        403,
        json={
            "error": "invalid_grant",
            "error_description": "code verifier mismatch",
        },
    )

    with pytest.raises(oauth.LoginError, match="code verifier mismatch"):
        sign_in(auth0)


def test_authorize_reports_an_unreachable_token_endpoint(
    auth0: Auth0, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(
        oauth,
        "_token_client",
        lambda: httpx.Client(transport=httpx.MockTransport(unreachable)),
    )

    with pytest.raises(oauth.LoginError) as failure:
        sign_in(auth0)

    assert str(failure.value) == (
        f"could not reach {TENANT.domain}: connection refused"
    )


def test_authorize_reports_a_token_response_that_is_not_json(
    auth0: Auth0,
) -> None:
    auth0.reply = httpx.Response(200, text="<html>captive portal</html>")

    with pytest.raises(oauth.LoginError, match="other than JSON"):
        sign_in(auth0)


def test_authorize_outlasts_a_connection_that_sends_no_request(
    auth0: Auth0, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oauth, "CONNECTION_TIMEOUT", 0.2)
    silent = socket.socket()

    def preconnect(state: str) -> list[dict[str, str]]:
        uri = httpx.URL(auth0.authorization["redirect_uri"])
        silent.connect((str(uri.host), uri.port or 0))
        return signed_in(state)

    auth0.redirect = preconnect
    try:
        tokens = sign_in(auth0)
    finally:
        silent.close()

    assert tokens.access_token == "access-1"


def test_authorize_stops_waiting_for_an_abandoned_sign_in(
    auth0: Auth0, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oauth, "LOGIN_TIMEOUT", 0.2)
    auth0.redirect = lambda state: []

    with pytest.raises(oauth.LoginError, match="no sign-in completed"):
        sign_in(auth0)


def test_authorize_blames_rejected_redirects_for_a_timed_out_sign_in(
    auth0: Auth0, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oauth, "LOGIN_TIMEOUT", 1.0)
    auth0.redirect = lambda state: [{"code": "stale", "state": "older"}]

    with pytest.raises(oauth.LoginError) as failure:
        sign_in(auth0)

    assert "1 redirect(s) carried another state" in str(failure.value)


def test_authorize_names_the_ports_it_could_not_bind(
    auth0: Auth0, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = [socket.create_server(("127.0.0.1", 0)) for _ in range(2)]
    ports = tuple(held.getsockname()[1] for held in taken)
    monkeypatch.setattr(oauth, "LOOPBACK_PORTS", ports)
    try:
        with pytest.raises(oauth.LoginError) as failure:
            sign_in(auth0)
    finally:
        for held in taken:
            held.close()

    assert str(ports[0]) in str(failure.value)
    assert str(ports[1]) in str(failure.value)
    assert "address already in use" in str(failure.value).lower()


def test_refresh_returns_a_rotated_refresh_token(auth0: Auth0) -> None:
    tokens = oauth.refresh(TENANT, "refresh-0")

    assert auth0.grant == {
        "grant_type": "refresh_token",
        "client_id": "client-1",
        "refresh_token": "refresh-0",
    }
    assert tokens.refresh_token == "refresh-1"
    assert tokens.access_token == "access-1"


def test_refresh_returns_no_token_when_auth0_keeps_the_old_one(
    auth0: Auth0,
) -> None:
    auth0.reply = httpx.Response(
        200, json={"access_token": "access-2", "expires_in": 3600}
    )

    tokens = oauth.refresh(TENANT, "refresh-0")

    assert tokens.refresh_token is None
    assert tokens.expires_in == 3600


def test_refresh_reports_a_revoked_refresh_token(auth0: Auth0) -> None:
    auth0.reply = httpx.Response(
        401, json={"error_description": "unknown or invalid refresh token"}
    )

    with pytest.raises(oauth.LoginError, match="invalid refresh token"):
        oauth.refresh(TENANT, "refresh-0")


@pytest.mark.parametrize(
    "api",
    [
        "http://localhost:8080/api/",
        "http://localhost:8080/api",
        "http://localhost:8080",
    ],
)
def test_tenant_config_signs_the_local_api_in_to_the_dev_tenant(
    monkeypatch: pytest.MonkeyPatch, api: str
) -> None:
    """Every spelling of the local API the SDK accepts, with nothing set:
    a developer runs `albus login` without configuring Auth0 first."""
    for env in (oauth.DOMAIN_ENV, oauth.CLIENT_ID_ENV, oauth.AUDIENCE_ENV):
        monkeypatch.delenv(env, raising=False)

    tenant = oauth.tenant_config(api)

    assert tenant == oauth.TenantConfig(
        domain="dev-kbhnwdz2wrg6jl1a.us.auth0.com",
        client_id="v3VYSQpG7oVGIKVsuf4QITtIB8G2lFCX",
        audience="https://api.albus.dev",
    )


def test_tenant_config_signs_the_default_api_in_to_the_production_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env in (oauth.DOMAIN_ENV, oauth.CLIENT_ID_ENV, oauth.AUDIENCE_ENV):
        monkeypatch.delenv(env, raising=False)

    tenant = oauth.tenant_config("https://albus.sh/api")

    assert tenant == oauth.TenantConfig(
        domain="albusgroup.us.auth0.com",
        client_id="AKj5qYBdhejMt3ztROUJDBtHThmXmQL1",
        audience="https://api.albus.sh",
    )


def test_tenant_config_overrides_a_known_tenant_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(oauth.DOMAIN_ENV, "local.us.auth0.com")
    monkeypatch.setenv(oauth.CLIENT_ID_ENV, "local-client")
    monkeypatch.setenv(oauth.AUDIENCE_ENV, "https://api.albus.local")

    tenant = oauth.tenant_config("http://localhost:8080/api")

    assert tenant == oauth.TenantConfig(
        domain="local.us.auth0.com",
        client_id="local-client",
        audience="https://api.albus.local",
    )


def test_authorize_leaves_opening_the_url_to_the_reader(
    auth0: Auth0, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--no-browser` announces the URL and launches nothing. The
    loopback listener still waits, because the reader's browser redirects
    back to it — here the announcement itself stands in for the reader
    opening the URL."""
    launched: list[str] = []
    monkeypatch.setattr(webbrowser, "open", launched.append)

    def visit(url: str) -> None:
        auth0.open(url)

    tokens = oauth.authorize(TENANT, visit, open_browser=False)

    assert tokens.access_token == "access-1"
    assert launched == []
