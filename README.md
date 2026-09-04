# Deploy and Host Pydantic AI on Railway

A typed AI agent runtime with persistent web chat and multi-provider model support.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/pydantic-ai?referralCode=indah&utm_medium=integration&utm_source=template&utm_campaign=generic)

## About Hosting Pydantic AI

This production-oriented starter runs a [Pydantic AI](https://pydantic.dev/docs/ai/) agent behind FastAPI. Complete Pydantic AI message histories are serialized with `ModelMessagesTypeAdapter` and stored in PostgreSQL, preserving tool calls, tool results, metadata, and provider-specific message parts across requests.

The application requires `DATABASE_URL`, but it can boot without an LLM API key. This lets the UI and database-backed health check run while provider configuration is completed.

## Common Use Cases

- Persistent customer or internal AI assistants
- Typed agent APIs with multi-turn context
- Provider evaluation across OpenAI, Anthropic, Google Gemini, and Groq
- A small foundation for adding domain tools, authentication, and observability

## Dependencies for Pydantic AI Hosting

- Python 3.12
- Pydantic AI
- FastAPI and Uvicorn
- PostgreSQL
- Psycopg 3 async connection pooling
- `uv` with a committed lockfile for reproducible dependency installation
- One API key for the selected model provider

Redis and application volumes are not required.

## Features

- Official Pydantic AI `message_history` and `all_messages()` flow
- Full history round-trip through `ModelMessagesTypeAdapter` and PostgreSQL JSONB
- Persistent conversations identified by UUID
- Browser chat with conversation ID persistence and a **New Chat** action
- Typed conversation and chat endpoints with OpenAPI docs at `/docs`
- Database-aware health endpoint that never calls an LLM
- Automatic lightweight schema initialization
- Reproducible multi-stage image running as a non-root user

## Persistent Conversation Memory

Each conversation is stored as one PostgreSQL row with a UUID, timestamps, and a JSONB document containing the complete Pydantic AI message list. History is serialized with `ModelMessagesTypeAdapter.dump_json()`, restored with `ModelMessagesTypeAdapter.validate_python()`, passed back through `Agent.run(message_history=...)`, and updated only after a successful agent run. Failed model requests therefore leave the last valid history untouched.

## Supported AI Providers

| `MODEL_PROVIDER` | Pydantic AI identifier | Credential |
|---|---|---|
| `openai` | `openai:<MODEL_NAME>` | `OPENAI_API_KEY` |
| `anthropic` | `anthropic:<MODEL_NAME>` | `ANTHROPIC_API_KEY` |
| `google` | `google:<MODEL_NAME>` | `GOOGLE_API_KEY` |
| `groq` | `groq:<MODEL_NAME>` | `GROQ_API_KEY` |

The current Pydantic AI Gemini API prefix is `google:`. Older `google-gla:` examples are not used by this starter.

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `DATABASE_URL` | Yes | none | PostgreSQL connection URL |
| `MODEL_PROVIDER` | Yes | `openai` | `openai`, `anthropic`, `google`, or `groq` |
| `MODEL_NAME` | Yes | `gpt-4o-mini` | Model name without provider prefix |
| Matching provider key | For chat | none | Credential listed in the provider table |
| `SYSTEM_PROMPT` | No | `You are a helpful AI assistant.` | Agent instructions |
| `REQUEST_TIMEOUT_SECONDS` | No | `60` | Per-model-request deadline |
| `HOST` | No | `0.0.0.0` | Network bind address |
| `PORT` | No | `8000` | HTTP port; Railway injects this |

`DB_POOL_MIN_SIZE`, `DB_POOL_MAX_SIZE`, and `DB_POOL_TIMEOUT` optionally tune the PostgreSQL pool; defaults of `1`, `10`, and 10 seconds are suitable for a small Railway service. `APP_API_KEY` optionally enables Bearer-token protection for chat and conversation APIs.

Copy `.env.example` to `.env` locally and replace the database credentials. Never commit `.env`.

## API Endpoints

- `GET /health` returns `{"status":"ok","database":"ok"}` after a database ping.
- `GET /api/config` returns public provider/model configuration without secrets.
- `POST /api/conversations` creates an empty conversation.
- `GET /api/conversations/{conversation_id}` returns metadata and complete serialized history.
- `DELETE /api/conversations/{conversation_id}` permanently deletes a conversation.
- `POST /api/chat` creates or continues a conversation.

Start a conversation:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello"}'
```

Continue it by including the returned UUID:

```json
{
  "message": "What did I just say?",
  "conversation_id": "2afacb61-29da-41fe-a9cc-ae2f536ee9f7"
}
```

Malformed UUIDs return `422`, unknown conversations return `404`, unavailable databases return `503`, provider failures return `502`, and timeouts return `504`.

## Web Interface

Open `/` on the deployed domain. The browser stores the active `conversation_id` in `localStorage` and sends it with later messages. **New Chat** clears that identifier, so the next message creates a separate PostgreSQL conversation.

## Railway Deployment

Create two services in one Railway project:

1. **PostgreSQL** — add Railway's PostgreSQL service. It stays on private networking, listens on port `5432`, and uses its Railway-managed persistent volume. It needs no public domain.
2. **Pydantic AI Agent** — deploy the GitHub source repository and generate a public domain. The container listens publicly on Railway's injected port (default `8000`).

Set these variables on the Pydantic AI service:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
MODEL_PROVIDER=openai
MODEL_NAME=gpt-4o-mini
OPENAI_API_KEY=your-secret-key
```

Set the health-check path to `/health`. The web UI is at `/`, and FastAPI/OpenAPI documentation is at `/docs`. Railway discovers the Dockerfile, so no custom start command is necessary. No Redis, application volume, or `RAILWAY_RUN_UID` is needed. Conversation history persists on the PostgreSQL service's managed volume.

For local development, create the database named in `.env`, then run:

```powershell
Copy-Item .env.example .env
uv sync --frozen
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Security Notes

- Keep `DATABASE_URL` and provider keys in Railway variables, never browser code.
- When `APP_API_KEY` is set, chat and conversation endpoints require `Authorization: Bearer <token>`. The built-in UI deliberately does not embed this secret, so token-protected deployments should use an authenticated API client or add their own secure login flow.
- Add authentication and conversation ownership before exposing stored histories publicly.
- This starter has no rate limiting, moderation, or usage quotas; add them before exposing a cost-bearing endpoint to untrusted users.
- Provider output is inserted with `textContent`, not raw HTML.
- `DELETE` is irreversible and should be protected by authentication in a public product.

## Pydantic AI vs Alternatives

| Project | Primary ecosystem | Strong fit | Trade-off for this starter |
|---|---|---|---|
| Pydantic AI | Python/Pydantic | Typed agents and structured histories | Provider behavior varies by model |
| Agno | Python | Broad agent, team, and knowledge tooling | More surface area than this runtime needs |
| Mastra | TypeScript | TypeScript-native agent workflows | Not a Python/Pydantic stack |
| CrewAI | Python | Role-based multi-agent orchestration | More orchestration than a single chat needs |

## Why Deploy Pydantic AI on Railway?

Railway provides the application build, private service networking, managed PostgreSQL, secrets, health checks, and a public domain in one project. The app remains stateless at the container layer while complete multi-turn conversation histories survive deployments in PostgreSQL.
