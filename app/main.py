from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from psycopg import Error as PsycopgError
from psycopg_pool import AsyncConnectionPool, PoolTimeout
from pydantic import BaseModel, Field

from app.agent import AgentConfigurationError, AgentProviderError, AgentTimeoutError, chat
from app.config import get_settings
from app.database import Conversation, ConversationNotFoundError, ConversationRepository

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"


class HealthResponse(BaseModel):
    status: str
    database: str


class ConfigResponse(BaseModel):
    provider: str
    model: str
    configured: bool


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: UUID
    model: str
    provider: str


class ConversationResponse(BaseModel):
    conversation_id: UUID
    created_at: datetime
    updated_at: datetime
    messages: list[dict[str, Any]]


class ErrorDetail(BaseModel):
    detail: str


def get_repository(request: Request) -> ConversationRepository:
    repository: ConversationRepository = request.app.state.repository
    return repository


def conversation_response(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse(
        conversation_id=conversation.id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=ConversationRepository.serialize_messages(conversation.messages),
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        min_size=1,
        max_size=10,
        open=False,
        timeout=10,
    )
    await pool.open(wait=True)
    try:
        repository = ConversationRepository(pool)
        await repository.initialize()
        application.state.repository = repository
        yield
    finally:
        await pool.close()


app = FastAPI(
    title="Pydantic AI Agent",
    description="A typed AI agent runtime with persistent conversations.",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def web_ui() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health", response_model=HealthResponse, responses={503: {"model": ErrorDetail}})
async def health(request: Request) -> HealthResponse:
    try:
        await get_repository(request).ping()
    except Exception as exc:
        logger.warning("Database health check failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return HealthResponse(status="ok", database="ok")


@app.get("/api/config", response_model=ConfigResponse)
async def config() -> ConfigResponse:
    settings = get_settings()
    try:
        _ = settings.model_identifier
        configured = settings.provider_api_key is not None
    except ValueError:
        configured = False
    return ConfigResponse(
        provider=settings.normalized_provider,
        model=settings.model_name,
        configured=configured,
    )


@app.post(
    "/api/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={503: {"model": ErrorDetail}},
)
async def create_conversation(request: Request) -> ConversationResponse:
    try:
        conversation = await get_repository(request).create()
    except (PsycopgError, PoolTimeout) as exc:
        logger.warning("Could not create conversation", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return conversation_response(conversation)


@app.get(
    "/api/conversations/{conversation_id}",
    response_model=ConversationResponse,
    responses={404: {"model": ErrorDetail}, 503: {"model": ErrorDetail}},
)
async def get_conversation(conversation_id: UUID, request: Request) -> ConversationResponse:
    try:
        conversation = await get_repository(request).get(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        ) from exc
    except (PsycopgError, PoolTimeout) as exc:
        logger.warning("Could not load conversation", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return conversation_response(conversation)


@app.delete(
    "/api/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorDetail}, 503: {"model": ErrorDetail}},
)
async def delete_conversation(conversation_id: UUID, request: Request) -> Response:
    try:
        await get_repository(request).delete(conversation_id)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        ) from exc
    except (PsycopgError, PoolTimeout) as exc:
        logger.warning("Could not delete conversation", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    responses={
        404: {"model": ErrorDetail},
        500: {"model": ErrorDetail},
        502: {"model": ErrorDetail},
        503: {"model": ErrorDetail},
        504: {"model": ErrorDetail},
    },
)
async def api_chat(payload: ChatRequest, request: Request) -> ChatResponse:
    repository = get_repository(request)
    try:
        conversation = (
            await repository.get(payload.conversation_id)
            if payload.conversation_id is not None
            else await repository.create()
        )
        result = await chat(
            payload.message,
            conversation.id,
            conversation.messages,
            get_settings(),
        )
        await repository.save_messages(conversation.id, result.messages)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found."
        ) from exc
    except AgentConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    except AgentTimeoutError as exc:
        logger.warning("Model request timed out", exc_info=True)
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except AgentProviderError as exc:
        logger.warning("Model provider request failed", exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except (PsycopgError, PoolTimeout) as exc:
        logger.warning("Database operation failed", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected chat failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the request.",
        ) from exc

    return ChatResponse(
        response=result.response,
        conversation_id=conversation.id,
        model=result.model,
        provider=result.provider,
    )
