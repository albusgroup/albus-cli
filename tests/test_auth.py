"""Which credential a command authenticates with, and what the CLI says
when it has none. The error strings are the deliverable: an agent that
is told the fix recovers, and one shown a status code stalls."""

import json
import re
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from albus_sdk import errors
from typer.testing import CliRunner

from albus_cli import client, credentials, oauth
from albus_cli.credentials import Credential
from albus_cli.main import app, main
from tests.conftest import FakeAlbus

runner = CliRunner()

BASE_URL = "https://albus.sh/api"
LOCAL_URL = "http://localhost:8080/api"
TENANT = oauth.TenantConfig(
    domain="albus.us.auth0.com", client_id="cli", audience="https://api"
)


@pytest.fixture(autouse=True)
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the credential store at tmp_path, and start signed out."""
    directory = tmp_path / "config"
    monkeypatch.setenv(credentials.CONFIG_DIR_ENV, str(directory))
    monkeypatch.delenv(credentials.XDG_CONFIG_HOME_ENV, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)
    return directory


@pytest.fixture
def signed_out(albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch) -> FakeAlbus:
    """The SDK fake, with the API key the shared fixture exports removed."""
    monkeypatch.delenv(client.API_KEY_ENV, raising=False)
    return albus


def stored(expires_in: float, refresh_token: str | None = "refresh") -> None:
    credentials.save(
        BASE_URL,
        Credential(
            access_token="stored-access",
            refresh_token=refresh_token,
            expires_at=time.time() + expires_in,
        ),
    )


def fails(monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
    """Drive `main`, where an exception becomes a reported message."""
    monkeypatch.setattr("sys.argv", ["albus", *argv])
    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1


def test_api_key_wins_over_a_stored_session(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")
    stored(expires_in=3600)

    result = runner.invoke(app, ["sessions", "list"])

    assert result.exit_code == 0, result.output
    security = albus.init_kwargs[0]["security"]
    assert security.api_key_auth == "env-key"
    assert security.bearer_auth is None


def test_stored_session_authenticates_with_a_bearer_token(
    signed_out: FakeAlbus,
) -> None:
    stored(expires_in=3600)

    result = runner.invoke(app, ["sessions", "list"])

    assert result.exit_code == 0, result.output
    security = signed_out.init_kwargs[0]["security"]
    assert security.bearer_auth == "stored-access"
    assert security.api_key_auth is None


def test_expired_session_is_refreshed_and_stored(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored(expires_in=-1)
    grants: list[str] = []

    def renew(tenant: oauth.TenantConfig, token: str) -> oauth.Tokens:
        grants.append(token)
        return oauth.Tokens(
            access_token="renewed-access",
            refresh_token=None,
            expires_in=3600,
        )

    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)
    monkeypatch.setattr(oauth, "refresh", renew)

    result = runner.invoke(app, ["sessions", "list"])

    assert result.exit_code == 0, result.output
    assert grants == ["refresh"]
    assert signed_out.init_kwargs[0]["security"].bearer_auth == "renewed-access"
    saved = credentials.load(BASE_URL)
    assert saved is not None
    assert saved.access_token == "renewed-access"
    # Auth0 returned no new refresh token, so the stored one stands.
    assert saved.refresh_token == "refresh"
    assert saved.expires_at > time.time()


def test_refresh_keeps_the_rotated_refresh_token(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored(expires_in=-1)
    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)
    monkeypatch.setattr(
        oauth,
        "refresh",
        lambda tenant, token: oauth.Tokens(
            access_token="renewed-access",
            refresh_token="rotated",
            expires_in=3600,
        ),
    )

    assert runner.invoke(app, ["sessions", "list"]).exit_code == 0
    saved = credentials.load(BASE_URL)
    assert saved is not None
    assert saved.refresh_token == "rotated"


def test_a_session_expiring_within_the_leeway_is_refreshed(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored(expires_in=client.EXPIRY_LEEWAY / 2)
    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)
    monkeypatch.setattr(
        oauth,
        "refresh",
        lambda tenant, token: oauth.Tokens(
            access_token="renewed-access",
            refresh_token=None,
            expires_in=3600,
        ),
    )

    assert runner.invoke(app, ["sessions", "list"]).exit_code == 0
    security = signed_out.init_kwargs[0]["security"]
    assert security.bearer_auth == "renewed-access"


def test_rejected_refresh_reports_an_expired_session(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stored(expires_in=-1)
    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)

    def revoked(tenant: oauth.TenantConfig, token: str) -> oauth.Tokens:
        raise oauth.LoginError("Auth0 refused the grant: invalid_grant")

    monkeypatch.setattr(oauth, "refresh", revoked)
    fails(monkeypatch, "sessions", "list")

    reported = capsys.readouterr().err
    assert "your session for https://albus.sh/api expired" in reported
    assert "invalid_grant" in reported
    assert "albus login" in reported


def test_expired_session_without_a_refresh_token_reports_it(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stored(expires_in=-1, refresh_token=None)
    fails(monkeypatch, "sessions", "list")

    reported = capsys.readouterr().err
    assert "expired" in reported
    assert "albus login" in reported


def test_no_credential_names_both_ways_to_get_one(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fails(monkeypatch, "sessions", "list")

    reported = capsys.readouterr().err
    assert "not signed in to https://albus.sh/api" in reported
    assert "albus login" in reported
    assert "ALBUS_API_KEY" in reported


def test_login_stores_the_session_and_names_the_account(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch, config_dir: Path
) -> None:
    announced: list[str] = []

    def authorize(tenant: oauth.TenantConfig, announce: object) -> oauth.Tokens:
        assert callable(announce)
        announce("https://albus.us.auth0.com/authorize?code_challenge=x")
        announced.append(tenant.client_id)
        return oauth.Tokens(
            access_token="fresh-access",
            refresh_token="fresh-refresh",
            expires_in=86400,
        )

    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)
    monkeypatch.setattr(oauth, "authorize", authorize)

    result = runner.invoke(app, ["login"])

    assert result.exit_code == 0, result.output
    assert announced == ["cli"]
    assert "https://albus.us.auth0.com/authorize" in result.output
    assert "Signed in as carlo@albus.sh" in result.output
    assert "https://albus.sh/api" in result.output
    assert str(config_dir / "credentials.json") in result.output
    saved = credentials.load(BASE_URL)
    assert saved is not None
    assert saved.refresh_token == "fresh-refresh"
    assert saved.expires_at == pytest.approx(time.time() + 86400, abs=30)
    # The account is resolved over the API with the new credential,
    # never by reading the token.
    assert signed_out.calls[-1].name == "whoami"
    assert signed_out.init_kwargs[-1]["security"].bearer_auth == "fresh-access"


def signs_in(
    monkeypatch: pytest.MonkeyPatch, refresh_token: str | None = "fresh-refresh"
) -> None:
    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)
    monkeypatch.setattr(
        oauth,
        "authorize",
        lambda tenant, announce: oauth.Tokens(
            access_token="fresh-access",
            refresh_token=refresh_token,
            expires_in=86400,
        ),
    )


def test_login_names_the_account_it_just_signed_in_as(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading the account back through precedence would name whoever
    the API key belongs to, under "Signed in as", and would 401 first:
    `/whoami` accepts a bearer token only."""
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")
    signs_in(monkeypatch)

    result = runner.invoke(app, ["login"])

    assert result.exit_code == 0, result.output
    assert "as carlo@albus.sh" in result.output
    assert albus.init_kwargs[-1]["security"].bearer_auth == "fresh-access"


def test_login_says_an_api_key_shadows_the_new_session(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")
    signs_in(monkeypatch)

    output = runner.invoke(app, ["login"]).output

    assert "ALBUS_API_KEY is set and takes precedence" in output
    assert "unset it" in output


def test_logout_says_an_api_key_still_authenticates(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")

    output = runner.invoke(app, ["logout"]).output

    assert "Signed out" in output
    assert "ALBUS_API_KEY is set and takes precedence" in output


def test_login_without_a_shadowing_key_says_nothing_about_one(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    signs_in(monkeypatch)

    assert client.API_KEY_ENV not in runner.invoke(app, ["login"]).output


def test_login_reports_a_session_auth0_cannot_renew(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No refresh token is a tenant misconfiguration, and `login` is the
    moment someone is present to fix it."""
    signs_in(monkeypatch, refresh_token=None)

    output = runner.invoke(app, ["login"]).output

    assert "no refresh token" in output
    assert "Allow Offline Access" in output


def test_login_spells_the_credential_path_from_home(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`~/.config/albus` is the path as its owner says it; the absolute
    one spends its first half on their username."""
    monkeypatch.setenv(
        credentials.CONFIG_DIR_ENV,
        str(tmp_path / "home" / ".config" / "albus"),
    )
    signs_in(monkeypatch)

    output = runner.invoke(app, ["login"]).output

    assert "~/.config/albus/credentials.json" in output
    assert str(tmp_path / "home") not in output


def test_login_styles_its_report_only_for_a_terminal(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Styling a report that is being piped or logged writes escapes into
    whatever reads it."""
    signs_in(monkeypatch)

    styled = runner.invoke(app, ["login"], color=True).output
    plain = runner.invoke(app, ["login"]).output

    assert "\x1b[32m" in styled
    assert "✓ Signed in as carlo@albus.sh" in strip_style(styled)
    assert "\x1b[" not in plain


def strip_style(output: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", output)


def test_a_rejected_api_key_is_not_told_to_sign_in(
    albus: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An instruction for the credential that was not used is worse than
    a vague one: it is followed, and leads nowhere."""
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")
    monkeypatch.setattr(albus.sessions, "list_sessions", unauthorized)
    fails(monkeypatch, "sessions", "list")

    reported = capsys.readouterr().err
    assert "the API key in ALBUS_API_KEY was rejected" in reported
    assert "https://albus.sh/api" in reported
    assert "albus login" not in reported.split("unset ALBUS_API_KEY")[0]


def test_a_rejected_session_says_to_sign_in_again(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stored(expires_in=3600)
    monkeypatch.setattr(signed_out.sessions, "list_sessions", unauthorized)
    fails(monkeypatch, "sessions", "list")

    reported = capsys.readouterr().err
    assert "your session for https://albus.sh/api was rejected" in reported
    assert "albus login" in reported
    assert "401" not in reported


def test_an_unwritable_store_names_the_file_and_the_way_out(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    config_dir: Path,
) -> None:
    """A read-only config directory is ordinary where agents run, and a
    traceback names no way out of it."""
    signs_in(monkeypatch)
    config_dir.parent.mkdir(parents=True, exist_ok=True)
    config_dir.parent.chmod(0o500)
    try:
        fails(monkeypatch, "login")
    finally:
        config_dir.parent.chmod(0o700)

    reported = capsys.readouterr().err
    assert str(credentials.path()) in reported
    assert "ALBUS_CONFIG_DIR" in reported


def refuses(body: str) -> Callable[..., None]:
    """A 403 as the generated SDK raises it: every undocumented status
    arrives as `AlbusDefaultError`, whose message carries the body."""

    def refuse(**kwargs: object) -> None:
        raise errors.AlbusDefaultError(
            "API error occurred",
            httpx.Response(
                403, text=body, headers={"content-type": "application/json"}
            ),
            body,
        )

    return refuse


def unauthorized(**kwargs: object) -> None:
    """A 401 as the generated SDK raises it, whose whole message is the
    server's `{"message": "unauthorized"}`."""
    raise errors.ErrUnauthorized(
        errors.ErrUnauthorizedData(message="unauthorized"),
        httpx.Response(401, text='{"message": "unauthorized"}'),
    )


def test_whoami_uses_the_session_over_an_api_key(
    albus: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")
    stored(expires_in=3600)

    assert runner.invoke(app, ["whoami"]).exit_code == 0
    security = albus.init_kwargs[0]["security"]
    assert security.bearer_auth == "stored-access"
    assert security.api_key_auth is None


def test_whoami_with_only_an_api_key_asks_for_a_sign_in(
    albus: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(client.API_KEY_ENV, "env-key")
    fails(monkeypatch, "whoami")

    reported = capsys.readouterr().err
    assert "needs a browser session" in reported
    assert "ALBUS_API_KEY cannot stand in" in reported
    assert "albus login" in reported
    assert albus.calls == []


def test_login_keys_the_session_by_the_base_url(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)
    monkeypatch.setattr(
        oauth,
        "authorize",
        lambda tenant, announce: oauth.Tokens(
            access_token="local-access",
            refresh_token=None,
            expires_in=86400,
        ),
    )

    result = runner.invoke(app, ["--base-url", LOCAL_URL, "login"])

    assert result.exit_code == 0, result.output
    assert credentials.load(BASE_URL) is None
    local = credentials.load(LOCAL_URL)
    assert local is not None
    assert local.access_token == "local-access"


def test_login_reports_an_unconfigured_tenant(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unconfigured(base_url: str) -> oauth.TenantConfig:
        raise oauth.LoginError(
            f"no Auth0 tenant configured for {base_url}: set "
            "ALBUS_AUTH0_CLIENT_ID"
        )

    monkeypatch.setattr(oauth, "tenant_config", unconfigured)
    fails(monkeypatch, "login")

    assert "no Auth0 tenant configured" in capsys.readouterr().err


def test_logout_forgets_the_session(signed_out: FakeAlbus) -> None:
    stored(expires_in=3600)

    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0, result.output
    assert "Signed out of https://albus.sh/api" in result.output
    assert credentials.load(BASE_URL) is None


def test_logout_without_a_session_is_not_an_error(
    signed_out: FakeAlbus, config_dir: Path
) -> None:
    result = runner.invoke(app, ["logout"])

    assert result.exit_code == 0, result.output
    assert "Signed out" in result.output
    assert not (config_dir / "credentials.json").exists()


def test_whoami_prints_the_account(signed_out: FakeAlbus) -> None:
    stored(expires_in=3600)

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["email"] == "carlo@albus.sh"
    assert signed_out.calls[0].name == "whoami"


def test_account_outside_the_beta_is_named_as_such(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stored(expires_in=3600)
    body = json.dumps(
        {
            "message": "this account is not part of the Albus beta",
            "code": "not_provisioned",
        }
    )

    monkeypatch.setattr(signed_out.auth, "whoami", refuses(body))

    fails(monkeypatch, "whoami")

    reported = capsys.readouterr().err
    assert "not in the Albus beta" in reported
    assert "carlo@albus.sh" in reported


def test_other_forbidden_responses_report_what_the_server_said(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The SDK's own message for an undocumented status repeats the
    status and appends the body, which reads as a developer's note."""
    stored(expires_in=3600)
    body = json.dumps({"message": "insufficient role", "code": "forbidden"})
    monkeypatch.setattr(signed_out.auth, "whoami", refuses(body))
    fails(monkeypatch, "whoami")

    reported = capsys.readouterr().err
    assert "403: insufficient role" in reported
    assert "Body:" not in reported


def test_unreadable_credentials_file_says_how_to_recover(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    config_dir: Path,
) -> None:
    """`load` treats a file it cannot read as "signed out", so the
    corrupt file only surfaces when `login` tries to write it."""
    config_dir.mkdir(parents=True)
    (config_dir / "credentials.json").write_text("not json")
    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)
    monkeypatch.setattr(
        oauth,
        "authorize",
        lambda tenant, announce: oauth.Tokens(
            access_token="fresh-access",
            refresh_token=None,
            expires_in=86400,
        ),
    )
    fails(monkeypatch, "login")

    reported = capsys.readouterr().err
    assert "is not a credentials file" in reported
    assert "Delete or repair it" in reported


def test_login_no_browser_announces_the_url_and_launches_nothing(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """How an agent signs in the user in front of it: it cannot click, so
    the URL is printed for the user and nothing is launched here."""
    opened: list[bool] = []

    def authorize(
        tenant: oauth.TenantConfig,
        announce: Callable[[str], None],
        open_browser: bool = True,
    ) -> oauth.Tokens:
        opened.append(open_browser)
        announce("https://albus.us.auth0.com/authorize?state=x")
        return oauth.Tokens(
            access_token="fresh-access",
            refresh_token="fresh-refresh",
            expires_in=86400,
        )

    monkeypatch.setattr(oauth, "tenant_config", lambda base_url: TENANT)
    monkeypatch.setattr(oauth, "authorize", authorize)

    result = runner.invoke(app, ["login", "--no-browser"])

    assert result.exit_code == 0, result.output
    assert opened == [False]
    assert "https://albus.us.auth0.com/authorize?state=x" in result.output
    assert "If it does not open" not in result.output


def test_login_ends_with_a_run_command_and_an_agent_handoff(
    signed_out: FakeAlbus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The last lines are where attention is highest: the one command
    that runs an agent, the sentence to paste into a coding agent, and
    the documentation URL each of those two readers needs."""
    signs_in(monkeypatch)

    output = runner.invoke(app, ["login"]).output

    assert "albus sessions run demo" in output
    assert "https://docs.albus.sh/agents/docs.md" in output
    assert output.rstrip().endswith("https://docs.albus.sh/agents/docs.md")


def test_a_reported_error_names_where_it_is_documented(
    signed_out: FakeAlbus,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An error the reader cannot act on is a dead end for an agent as
    much as a person, so every one names the page documenting it."""
    fails(monkeypatch, "sessions", "list")

    assert (
        "https://docs.albus.sh/guides/troubleshooting" in capsys.readouterr().err
    )
