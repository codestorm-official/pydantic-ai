import asyncio
from dataclasses import dataclass
from uuid import UUID

from pydantic_ai import Agent, ModelMessage
from pydantic_ai.exceptions import AgentRunError, ModelAPIError

from app.config import Settings


class AgentConfigurationError(RuntimeError):
    """Raised when the selected agent cannot be configured."""


class AgentProviderError(RuntimeError):
    """Raised when a model provider request fails."""


class AgentTimeoutError(RuntimeError):
    """Raised when a model request exceeds its configured deadline."""


@dataclass(frozen=True)
class ChatResult:
    response: str
    model: str
    provider: str
    messages: list[ModelMessage]


def build_agent(settings: Settings) -> Agent[None, str]:
    try:
        identifier = settings.model_identifier
    except ValueError as exc:
        raise AgentConfigurationError(str(exc)) from exc
    if settings.provider_api_key is None:
        raise AgentConfigurationError(
            f"Missing {settings.provider_key_name} for provider '{settings.normalized_provider}'."
        )
    return Agent(identifier, instructions=settings.system_prompt)


async def chat(
    message: str,
    conversation_id: UUID,
    message_history: list[ModelMessage],
    settings: Settings,
) -> ChatResult:
    agent = build_agent(settings)
    try:
        result = await asyncio.wait_for(
            agent.run(
                message,
                message_history=message_history,
                conversation_id=str(conversation_id),
            ),
            timeout=settings.request_timeout_seconds,
        )
    except TimeoutError as exc:
        timeout = settings.request_timeout_seconds
        raise AgentTimeoutError(
            f"The model provider did not respond within {timeout:g} seconds."
        ) from exc
    except ModelAPIError as exc:
        raise AgentProviderError(
            "The model provider rejected or could not process the request."
        ) from exc
    except AgentRunError as exc:
        raise AgentProviderError(
            "The agent could not complete the request."
        ) from exc

    return ChatResult(
        response=result.output,
        model=settings.model_name,
        provider=settings.normalized_provider,
        messages=result.all_messages(),
    )
