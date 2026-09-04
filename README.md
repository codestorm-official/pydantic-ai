# Deploy and Host Pydantic AI Agent on Railway

A typed AI agent runtime with web chat and multi-provider model support.

## About Hosting Pydantic AI Agent

This repository is a small production-oriented starter for running a [Pydantic AI](https://pydantic.dev/docs/ai/) agent on Railway. FastAPI exposes a browser chat and typed JSON API, while Pydantic AI handles the provider-specific model runtime. The app boots without credentials so Railway health checks and the UI remain available while configuration is being completed.

## Common Use Cases

- Add an AI assistant to an internal tool or product prototype.
- Start a typed agent API before adding domain-specific tools and dependencies.
- Evaluate OpenAI, Anthropic, Google Gemini, or Groq through one small deployment.
- Host a stateless chat endpoint without operating a database or queue.

## Dependencies for Pydantic AI Agent Hosting

- Python 3.12
- Pydantic AI
- FastAPI and Uvicorn
- `uv` for dependency management
- One API key for the selected AI provider

No Postgres, Redis, persistent volume, or other Railway service is required.

## Features

- Pydantic AI `Agent` runtime with a configurable system prompt
- Responsive, dependency-free browser chat at `/`
- Typed request and response schemas with automatic OpenAPI docs at `/docs`
- Four selectable model providers
- Lightweight health check that never calls an LLM
- Clear configuration, timeout, validation, and provider errors
- Multi-stage container build running as a non-root user

## Supported AI Providers

| `MODEL_PROVIDER` | Pydantic AI identifier | Credential |
|---|---|---|
| `openai` | `openai:<MODEL_NAME>` | `OPENAI_API_KEY` |
| `anthropic` | `anthropic:<MODEL_NAME>` | `ANTHROPIC_API_KEY` |
| `google` | `google:<MODEL_NAME>` | `GOOGLE_API_KEY` |
| `groq` | `groq:<MODEL_NAME>` | `GROQ_API_KEY` |

The `google:` prefix follows current Pydantic AI documentation for the Gemini API. Older examples may use `google-gla:`; that is not used by the current provider interface.

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `MODEL_PROVIDER` | Yes | `openai` | One of `openai`, `anthropic`, `google`, `groq` |
| `MODEL_NAME` | Yes | `gpt-4o-mini` | Provider model name, without a prefix |
| Provider API key | Yes for chat | — | The matching credential from the table above |
| `SYSTEM_PROMPT` | No | `You are a helpful AI assistant.` | Agent instructions |
| `REQUEST_TIMEOUT_SECONDS` | No | `60` | Per-request deadline |
| `HOST` | No | `0.0.0.0` | Bind address |
| `PORT` | No | `8000` | Listening port; Railway injects this |

Copy `.env.example` to `.env` for local development. Do not commit `.env` or expose provider keys in client-side code.

## API Endpoints

- `GET /health` → `{"status":"ok"}` without contacting a provider.
- `GET /api/config` → public provider/model metadata and a `configured` flag; never returns keys.
- `POST /api/chat` accepts `{"message":"Hello"}` and returns `{"response":"...","model":"...","provider":"..."}`.
- `GET /docs` provides interactive OpenAPI documentation.

Example:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello"}'
```

Malformed input returns `422`; missing configuration returns `500`; upstream provider failures return `502`; and timeouts return `504`. Responses do not contain stack traces.

## Web Interface

Open `http://localhost:8000/` or the generated Railway domain. The lightweight HTML/CSS/JavaScript interface submits directly to `/api/chat`; no frontend build is required. Each request is independent—this starter does not persist conversation history.

## Railway Deployment

1. Push this repository to GitHub.
2. In Railway, choose **New Project → Deploy from GitHub repo** and select it.
3. Add `MODEL_PROVIDER`, `MODEL_NAME`, and the matching provider API key under **Variables**.
4. Deploy. Railway detects the root `Dockerfile`; no custom start command is needed.
5. In the service settings, generate a public domain.
6. Optionally set the health-check path to `/health`.

The container binds to `0.0.0.0` and reads Railway's injected `PORT`. Do not manually define a conflicting port. No volume, Postgres, Redis, or `RAILWAY_RUN_UID` variable is necessary.

For local development:

```bash
cp .env.example .env
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

On PowerShell, use `Copy-Item .env.example .env` instead of `cp` if preferred.

## Security Notes

- Store API keys as Railway variables and never put them in Git or browser code.
- The starter has no user authentication, rate limiting, moderation, or usage quotas. Add these before exposing a cost-bearing endpoint to untrusted users.
- `/api/config` reveals only the selected provider/model and whether its key exists.
- Provider output is displayed with `textContent`, not raw HTML.

## Pydantic AI vs Alternatives

| Project | Primary ecosystem | Strong fit | Trade-off for this starter |
|---|---|---|---|
| Pydantic AI | Python/Pydantic | Typed agent applications and structured outputs | Provider behavior still varies by model |
| Agno | Python | Broad agent, team, and knowledge tooling | More surface area than a minimal runtime needs |
| Mastra | TypeScript | TypeScript-native agent workflows | Not a Python/Pydantic stack |
| CrewAI | Python | Role-based multi-agent orchestration | More orchestration than a single chat agent needs |

The comparison is architectural, not a claim that one framework is universally better.

## Why Deploy Pydantic AI on Railway?

Railway can build the checked-in Dockerfile, supply secrets and `PORT`, monitor `/health`, and attach a public domain without provisioning supporting infrastructure. This makes the template useful as a clean base: deploy the stateless agent first, then add tools, authentication, persistence, or observability only when the product requires them.
