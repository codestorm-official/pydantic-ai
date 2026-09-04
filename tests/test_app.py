from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter, ModelRequest, ModelResponse
from pydantic_ai.messages import TextPart, UserPromptPart

import app.main as main_module
from app.agent import ChatResult
from app.config import get_settings
from app.database import Conversation, ConversationNotFoundError, ConversationRepository
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeRepository:
    def __init__(self) -> None:
        self.conversations: dict[UUID, Conversation] = {}

    async def ping(self) -> None:
        return None

    async def create(self, conversation_id: UUID | None = None) -> Conversation:
        now = datetime.now(UTC)
        conversation = Conversation(conversation_id or uuid4(), now, now, [])
        self.conversations[conversation.id] = conversation
        return conversation

    async def get(self, conversation_id: UUID) -> Conversation:
        try:
            return self.conversations[conversation_id]
        except KeyError as exc:
            raise ConversationNotFoundError(str(conversation_id)) from exc

    async def save_messages(
        self, conversation_id: UUID, messages: list[ModelMessage]
    ) -> Conversation:
        existing = await self.get(conversation_id)
        conversation = Conversation(
            existing.id,
            existing.created_at,
            datetime.now(UTC),
            ModelMessagesTypeAdapter.validate_json(
                ModelMessagesTypeAdapter.dump_json(messages)
            ),
        )
        self.conversations[conversation_id] = conversation
        return conversation

    async def delete(self, conversation_id: UUID) -> None:
        if self.conversations.pop(conversation_id, None) is None:
            raise ConversationNotFoundError(str(conversation_id))


@pytest.fixture
def repository(monkeypatch: pytest.MonkeyPatch) -> FakeRepository:
    monkeypatch.setenv("DATABASE_URL", "postgresql://ignored/for-tests")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    value = FakeRepository()
    app.state.repository = value
    return value


@pytest.fixture
def client(repository: FakeRepository) -> Iterator[TestClient]:
    del repository
    # Lifespan is intentionally skipped: endpoint tests inject their repository.
    yield TestClient(app, raise_server_exceptions=False)


def history(user_text: str, assistant_text: str) -> list[ModelMessage]:
    return [
        ModelRequest(parts=[UserPromptPart(content=user_text)]),
        ModelResponse(parts=[TextPart(content=assistant_text)]),
    ]


def test_application_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert {"/", "/health", "/api/chat", "/api/conversations"} <= paths


@pytest.mark.anyio
async def test_application_startup_initializes_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class FakePool:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        async def open(self, *, wait: bool) -> None:
            assert wait is True
            events.append("open")

        async def close(self) -> None:
            events.append("close")

    class StartupRepository:
        def __init__(self, pool: FakePool) -> None:
            del pool

        async def initialize(self) -> None:
            events.append("initialize")

    monkeypatch.setenv("DATABASE_URL", "postgresql://ignored/for-tests")
    get_settings.cache_clear()
    monkeypatch.setattr(main_module, "AsyncConnectionPool", FakePool)
    monkeypatch.setattr(main_module, "ConversationRepository", StartupRepository)
    async with main_module.lifespan(app):
        assert events == ["open", "initialize"]
    assert events == ["open", "initialize", "close"]


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_conversation_creation(client: TestClient) -> None:
    response = client.post("/api/conversations")
    assert response.status_code == 201
    assert response.json()["messages"] == []


@pytest.mark.anyio
async def test_storing_and_reloading_complete_history(repository: FakeRepository) -> None:
    conversation = await repository.create()
    expected = history("Hello", "Hi")
    await repository.save_messages(conversation.id, expected)
    loaded = await repository.get(conversation.id)
    assert ModelMessagesTypeAdapter.dump_json(loaded.messages) == (
        ModelMessagesTypeAdapter.dump_json(expected)
    )
    serialized = ConversationRepository.serialize_messages(loaded.messages)
    assert ModelMessagesTypeAdapter.validate_python(serialized) == expected


def test_new_and_continuing_conversation(
    client: TestClient,
    repository: FakeRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_history_lengths: list[int] = []

    async def fake_chat(
        message: str,
        conversation_id: UUID,
        message_history: list[ModelMessage],
        settings: Any,
    ) -> ChatResult:
        del conversation_id, settings
        seen_history_lengths.append(len(message_history))
        updated = message_history + history(message, f"Reply to {message}")
        return ChatResult("Reply", "test-model", "openai", updated)

    monkeypatch.setattr(main_module, "chat", fake_chat)
    first = client.post("/api/chat", json={"message": "Hello"})
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]
    assert UUID(conversation_id) in repository.conversations

    second = client.post(
        "/api/chat",
        json={"message": "Continue", "conversation_id": conversation_id},
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id
    assert seen_history_lengths == [0, 2]
    assert len(repository.conversations[UUID(conversation_id)].messages) == 4


def test_invalid_and_unknown_conversation_id(client: TestClient) -> None:
    assert client.get("/api/conversations/not-a-uuid").status_code == 422
    assert client.get(f"/api/conversations/{uuid4()}").status_code == 404


def test_missing_model_api_key(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": "Hello"})
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Missing OPENAI_API_KEY for provider 'openai'."
    }


def test_database_failure_returns_503(client: TestClient) -> None:
    async def broken_ping() -> None:
        raise OperationalError("connection failed")

    app.state.repository.ping = broken_ping
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable."}
