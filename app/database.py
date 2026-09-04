from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter


class ConversationNotFoundError(LookupError):
    """Raised when a conversation does not exist."""


@dataclass(frozen=True)
class Conversation:
    id: UUID
    created_at: datetime
    updated_at: datetime
    messages: list[ModelMessage]


class ConversationRepository:
    """Async PostgreSQL persistence for complete Pydantic AI histories."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def initialize(self) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id UUID PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    message_history JSONB NOT NULL DEFAULT '[]'::jsonb
                )
                """
            )

    async def ping(self) -> None:
        async with self._pool.connection() as connection:
            await connection.execute("SELECT 1")

    async def create(self, conversation_id: UUID | None = None) -> Conversation:
        identifier = conversation_id or uuid4()
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO conversations (id)
                VALUES (%s)
                RETURNING id, created_at, updated_at, message_history
                """,
                (identifier,),
            )
            row = await cursor.fetchone()
        assert row is not None
        return self._from_row(row)

    async def get(self, conversation_id: UUID) -> Conversation:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT id, created_at, updated_at, message_history
                FROM conversations
                WHERE id = %s
                """,
                (conversation_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise ConversationNotFoundError(str(conversation_id))
        return self._from_row(row)

    async def save_messages(
        self, conversation_id: UUID, messages: list[ModelMessage]
    ) -> Conversation:
        serialized = json.loads(ModelMessagesTypeAdapter.dump_json(messages))
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                UPDATE conversations
                SET message_history = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id, created_at, updated_at, message_history
                """,
                (Jsonb(serialized), conversation_id),
            )
            row = await cursor.fetchone()
        if row is None:
            raise ConversationNotFoundError(str(conversation_id))
        return self._from_row(row)

    async def delete(self, conversation_id: UUID) -> None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "DELETE FROM conversations WHERE id = %s", (conversation_id,)
            )
        if cursor.rowcount == 0:
            raise ConversationNotFoundError(str(conversation_id))

    @staticmethod
    def serialize_messages(messages: list[ModelMessage]) -> list[dict[str, Any]]:
        value: Any = json.loads(ModelMessagesTypeAdapter.dump_json(messages))
        if not isinstance(value, list):
            raise ValueError("Serialized message history must be a list.")
        return value

    @staticmethod
    def _from_row(row: tuple[Any, ...]) -> Conversation:
        identifier, created_at, updated_at, raw_history = row
        messages = ModelMessagesTypeAdapter.validate_python(raw_history)
        return Conversation(
            id=identifier,
            created_at=created_at,
            updated_at=updated_at,
            messages=messages,
        )
