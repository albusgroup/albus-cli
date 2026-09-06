"""Fakes standing in for the SDK client so tests stay offline."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from albus_sdk import models, operations

import albus_cli.client


def session() -> models.Session:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return models.Session(
        id="s1",
        state="DONE",
        invocation_count=1,
        created_at=now,
        updated_at=now,
    )


def assistant_message() -> models.SessionMessage:
    return models.SessionMessage(
        cursor=1,
        invocation_key="inv-1",
        role="assistant",
        content="hello back",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def invite() -> models.Invite:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return models.Invite(
        id="i1",
        email="new@example.com",
        role="member",
        expires_at=now,
        created_at=now,
    )


def member() -> models.OrganizationMember:
    return models.OrganizationMember(
        user_id="u1",
        email="carlo@albus.sh",
        name="Carlo",
        role="admin",
        joined_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def organization() -> models.Organization:
    return models.Organization(
        id="o1", name="Albus", created_at=datetime(2026, 1, 1, tzinfo=UTC)
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
    # An invocation that has not answered yet returns no message, which is
    # what a `--no-wait` invocation gets.
    message: models.SessionMessage | None = field(
        default_factory=assistant_message
    )

    def run_session(self, **kwargs: Any) -> operations.RunSessionResponse:
        self.calls.append(Call("run_session", kwargs))
        return operations.RunSessionResponse(
            headers=self.headers,
            result=models.RunSessionResponse(
                session=session(), message=self.message
            ),
        )

    def list_sessions(self, **kwargs: Any) -> models.ListSessionsResponse:
        self.calls.append(Call("list_sessions", kwargs))
        return models.ListSessionsResponse(sessions=[session()])

    def cancel_session(self, **kwargs: Any) -> models.CancelSessionResponse:
        self.calls.append(Call("cancel_session", kwargs))
        return models.CancelSessionResponse(invocation_key="inv-1")


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
        return invite()

    def list_invites(self, **kwargs: Any) -> models.ListInvitesResponse:
        self.calls.append(Call("list_invites", kwargs))
        return models.ListInvitesResponse(invites=[invite()])

    def revoke_invite(self, **kwargs: Any) -> None:
        self.calls.append(Call("revoke_invite", kwargs))


@dataclass
class FakeAuth:
    calls: list[Call]

    def whoami(self, **kwargs: Any) -> models.WhoamiResponse:
        self.calls.append(Call("whoami", kwargs))
        albus = models.OrganizationMembership(
            id="o1", name="Albus", roles=["admin"]
        )
        return models.WhoamiResponse(
            user=models.AuthenticatedUser(
                user_id="u1",
                email="carlo@albus.sh",
                organizations=[albus],
                active_organization=albus,
            )
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
class FakeMemories:
    calls: list[Call]

    def list_memory_groups(
        self, **kwargs: Any
    ) -> models.ListMemoryGroupsResponse:
        self.calls.append(Call("list_memory_groups", kwargs))
        return models.ListMemoryGroupsResponse(
            memory_groups=[
                models.MemoryGroup(
                    key="team-a",
                    active_memories=2,
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ]
        )

    def list_memories(self, **kwargs: Any) -> models.ListMemoriesResponse:
        self.calls.append(Call("list_memories", kwargs))
        return models.ListMemoriesResponse(
            memories=[
                models.Memory(
                    id="m1",
                    content="prefers terse answers",
                    status="active",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ]
        )

    def delete_memory(self, **kwargs: Any) -> None:
        self.calls.append(Call("delete_memory", kwargs))

    def delete_memory_group(self, **kwargs: Any) -> None:
        self.calls.append(Call("delete_memory_group", kwargs))


@dataclass
class FakeTraces:
    calls: list[Call]

    def list_traces(self, **kwargs: Any) -> models.ListTracesResponse:
        self.calls.append(Call("list_traces", kwargs))
        return models.ListTracesResponse(
            traces=[
                models.TraceSummary(
                    invocation_key="inv-1",
                    session_id="s1",
                    status="SUCCEEDED",
                    spans_expired=False,
                    started_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ]
        )

    def get_trace(self, **kwargs: Any) -> operations.GetTraceResponse:
        self.calls.append(Call("get_trace", kwargs))
        return operations.GetTraceResponse(
            headers={},
            result=models.TraceResponse(
                invocation_key="inv-1",
                session_id="s1",
                status="SUCCEEDED",
                spans_expired=False,
                started_at=datetime(2026, 1, 1, tzinfo=UTC),
                session_position=1,
                spans=[],
            ),
        )


@dataclass
class FakeOrganization:
    calls: list[Call]

    def get_organization(self, **kwargs: Any) -> models.Organization:
        self.calls.append(Call("get_organization", kwargs))
        return organization()

    def update_organization(self, **kwargs: Any) -> models.Organization:
        self.calls.append(Call("update_organization", kwargs))
        return organization()

    def list_organization_members(
        self, **kwargs: Any
    ) -> models.ListOrganizationMembersResponse:
        self.calls.append(Call("list_organization_members", kwargs))
        return models.ListOrganizationMembersResponse(members=[member()])

    def set_organization_member_role(
        self, **kwargs: Any
    ) -> models.OrganizationMember:
        self.calls.append(Call("set_organization_member_role", kwargs))
        return member()

    def remove_organization_member(self, **kwargs: Any) -> None:
        self.calls.append(Call("remove_organization_member", kwargs))


@dataclass
class FakeBilling:
    calls: list[Call]

    def get_credit_balance(self, **kwargs: Any) -> models.CreditBalanceResponse:
        self.calls.append(Call("get_credit_balance", kwargs))
        return models.CreditBalanceResponse(balance_usd="12.50")

    def list_credit_ledger(
        self, **kwargs: Any
    ) -> models.ListCreditLedgerResponse:
        self.calls.append(Call("list_credit_ledger", kwargs))
        return models.ListCreditLedgerResponse(
            entries=[
                models.CreditLedgerEntry(
                    kind="purchase",
                    amount_usd="20.00",
                    reference="cs_1",
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ]
        )

    def create_checkout(self, **kwargs: Any) -> models.CreateCheckoutResponse:
        self.calls.append(Call("create_checkout", kwargs))
        return models.CreateCheckoutResponse(
            url="https://checkout.example.com/cs_1"
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
        self.memories = FakeMemories(self.calls)
        self.traces = FakeTraces(self.calls)
        self.organization = FakeOrganization(self.calls)
        self.billing = FakeBilling(self.calls)

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
