"""Fakes standing in for the SDK client so tests stay offline."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from albus_sdk import models

import albus_cli.client


def session_response() -> models.SessionResponse:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return models.SessionResponse(
        session=models.Session(
            id="s1",
            state="DONE",
            invocation_count=1,
            created_at=now,
            updated_at=now,
        ),
        messages=[],
    )


def token() -> models.Token:
    return models.Token(
        id="t1", name="ci", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )


@dataclass
class Call:
    name: str
    kwargs: dict[str, Any]


@dataclass
class FakeSessions:
    calls: list[Call]
    headers: dict[str, list[str]] = field(
        default_factory=lambda: {"idempotency-key": ["inv-1"]}
    )

    def run_session(self, **kwargs: Any) -> models.RunSessionResponse:
        self.calls.append(Call("run_session", kwargs))
        return models.RunSessionResponse(
            headers=self.headers,
            result=session_response(),
        )

    def list_sessions(self, **kwargs: Any) -> models.ListSessionsResponse:
        self.calls.append(Call("list_sessions", kwargs))
        return models.ListSessionsResponse(sessions=[session_response().session])


@dataclass
class FakeSecrets:
    calls: list[Call]

    def create_secret(self, **kwargs: Any) -> models.Secret:
        self.calls.append(Call("create_secret", kwargs))
        return models.Secret(name="k", masked_value="...")


@dataclass
class FakeTokens:
    calls: list[Call]

    def list_tokens(self, **kwargs: Any) -> models.ListTokensResponse:
        self.calls.append(Call("list_tokens", kwargs))
        return models.ListTokensResponse(tokens=[token()])

    def create_token(self, **kwargs: Any) -> models.CreateTokenResponse:
        self.calls.append(Call("create_token", kwargs))
        return models.CreateTokenResponse(
            id="t1",
            name="ci",
            token="alb-t1-secret",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def get_token(self, **kwargs: Any) -> models.Token:
        self.calls.append(Call("get_token", kwargs))
        return token()

    def delete_token(self, **kwargs: Any) -> None:
        self.calls.append(Call("delete_token", kwargs))


@dataclass
class FakeHealth:
    calls: list[Call]

    def health(self, **kwargs: Any) -> models.HealthResponse:
        self.calls.append(Call("health", kwargs))
        return models.HealthResponse(status="ok")


@dataclass
class FakeInvites:
    calls: list[Call]

    def create_invite(self, **kwargs: Any) -> models.Invite:
        self.calls.append(Call("create_invite", kwargs))
        return models.Invite(id="i1", email="new@example.com", role="member")


@dataclass
class FakeAuth:
    calls: list[Call]

    def whoami(self, **kwargs: Any) -> models.WhoamiResponse:
        self.calls.append(Call("whoami", kwargs))
        return models.WhoamiResponse(
            user_id="u1",
            email="carlo@albus.sh",
            organizations=[
                models.OrganizationMembership(
                    id="o1", name="Albus", roles=["owner"]
                )
            ],
        )


@dataclass
class FakeModels:
    calls: list[Call]

    def list_models(self, **kwargs: Any) -> models.ListModelsResponse:
        self.calls.append(Call("list_models", kwargs))
        return models.ListModelsResponse(
            models=[
                models.ModelMeta(name="claude-opus-4-8", provider="anthropic")
            ]
        )


@dataclass
class FakeAlbus:
    init_kwargs: list[dict[str, Any]] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.sessions = FakeSessions(self.calls)
        self.secrets = FakeSecrets(self.calls)
        self.auth = FakeAuth(self.calls)
        self.tokens = FakeTokens(self.calls)
        self.health = FakeHealth(self.calls)
        self.invites = FakeInvites(self.calls)
        self.models = FakeModels(self.calls)

    def __call__(self, **kwargs: Any) -> "FakeAlbus":
        self.init_kwargs.append(kwargs)
        return self


@pytest.fixture(autouse=True)
def unstyled_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render command output without terminal styling.

    Typer styles an option name as several spans, so a styled render
    splits `--agent-file` into `-`, `-agent`, and `-file` around escape
    sequences and an assertion on the name stops matching. Styling is on
    whenever Rich believes it writes to a terminal, which it does under
    GitHub Actions; `dumb` is how it is told otherwise.
    """
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture
def albus(monkeypatch: pytest.MonkeyPatch) -> FakeAlbus:
    monkeypatch.setenv("ALBUS_API_KEY", "test-key")
    monkeypatch.delenv("ALBUS_BASE_URL", raising=False)
    fake = FakeAlbus()
    monkeypatch.setattr(albus_cli.client, "Albus", fake)
    return fake
