import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.agent import AgentConfigurationError, AgentProviderError, AgentTimeoutError, chat
from app.config import get_settings

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(
    title="Pydantic AI Agent",
    description="A typed AI agent runtime with multi-provider model support.",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    status: str


class ConfigResponse(BaseModel):
    provider: str
    model: str
    configured: bool


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)


class ChatResponse(BaseModel):
    response: str
    model: str
    provider: str


class ErrorDetail(BaseModel):
    detail: str


@app.get("/", include_in_schema=False)
async def web_ui() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


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
    "/api/chat",
    response_model=ChatResponse,
    responses={
        500: {"model": ErrorDetail},
        502: {"model": ErrorDetail},
        504: {"model": ErrorDetail},
    },
)
async def api_chat(request: ChatRequest) -> ChatResponse:
    try:
        result = await chat(request.message, get_settings())
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
    except Exception as exc:
        logger.exception("Unexpected chat failure")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the request.",
        ) from exc

    return ChatResponse(response=result.response, model=result.model, provider=result.provider)
