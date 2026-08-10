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


@dataclass
class Call:
    name: str
    kwargs: dict[str, Any]


@dataclass
class FakeSessions:
    calls: list[Call]

    def run_session(self, **kwargs: Any) -> models.RunSessionResponse:
        self.calls.append(Call("run_session", kwargs))
        return models.RunSessionResponse(
            headers={"idempotency-key": ["inv-1"]},
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
class FakeAlbus:
    init_kwargs: list[dict[str, Any]] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.sessions = FakeSessions(self.calls)
        self.secrets = FakeSecrets(self.calls)

    def __call__(self, **kwargs: Any) -> "FakeAlbus":
        self.init_kwargs.append(kwargs)
        return self


@pytest.fixture
def albus(monkeypatch: pytest.MonkeyPatch) -> FakeAlbus:
    monkeypatch.setenv("ALBUS_API_KEY", "test-key")
    monkeypatch.delenv("ALBUS_BASE_URL", raising=False)
    fake = FakeAlbus()
    monkeypatch.setattr(albus_cli.client, "Albus", fake)
    return fake
