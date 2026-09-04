import os
from uuid import uuid4

import pytest
from psycopg_pool import AsyncConnectionPool
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter, ModelRequest, ModelResponse
from pydantic_ai.messages import TextPart, UserPromptPart

from app.database import ConversationRepository

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
@pytest.mark.anyio
async def test_postgresql_history_survives_repository_reload() -> None:
    assert TEST_DATABASE_URL is not None
    pool = AsyncConnectionPool(TEST_DATABASE_URL, open=False)
    await pool.open(wait=True)
    try:
        first_repository = ConversationRepository(pool)
        await first_repository.initialize()
        conversation = await first_repository.create(uuid4())
        expected: list[ModelMessage] = [
            ModelRequest(parts=[UserPromptPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi")]),
        ]
        await first_repository.save_messages(conversation.id, expected)

        reloaded = await ConversationRepository(pool).get(conversation.id)
        assert ModelMessagesTypeAdapter.dump_json(reloaded.messages) == (
            ModelMessagesTypeAdapter.dump_json(expected)
        )
        await first_repository.delete(conversation.id)
    finally:
        await pool.close()
