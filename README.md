# LLM Guardrails API

A FastAPI + LangGraph chat API that puts deterministic guardrails around a Gemini model: prompt-injection filtering, PII masking, output validation, rate limiting, caching, and tracing.

![Request flow](docs/guardrails-flow.gif)

## How it works

```
Client → Rate limiter → Input guardrails → Cache → LangGraph agent → Output validator → Response
                         (clean, injection,         (primary → fallback)  (PII + harmful
                          PII masking)                                     content check)
```

## Features

- **Input guardrails:** delimiter cleaning, prompt-injection detection, and PII masking (email, phone, SSN, card, IP) before anything reaches the LLM
- **Output validation:** masks leaked PII and blocks harmful content in responses
- **Resilience:** LangGraph agent with primary model, fallback model, and graceful error handling
- **Performance:** per-IP rate limiting and a TTL response cache
- **Observability:** structured JSON logs, a `/metrics` endpoint, and LangSmith tracing with PII masked in traces
- **Deployment:** Dockerfile and `render.yml` for one-click deploys on Render

## Tech stack

FastAPI · LangGraph · Gemini · LangSmith · slowapi · pydantic-settings · uv · Docker · Render

## Quick start

```bash
git clone https://github.com/Shreek195/Production-LLM-Guardrail-API.git
cd Production-LLM-Guardrail-API

uv sync
cp .env.example .env        # add your GEMINI_API_KEY (and LANGSMITH_API_KEY for tracing)

uv run uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** to try it.

Or with Docker:

```bash
docker compose up --build
```

## API

### `POST /chat`

```json
{
  "message": "My email is test@example.com. In one sentence, why do LLM apps need guardrails?",
  "thread_id": "demo"
}
```

```json
{
  "response": "...",
  "model_used": "primary",
  "cached": false,
  "security_notes": ["Input PII masked: ['email']"]
}
```

A prompt-injection attempt returns `400`:

```json
{ "detail": "Your message was blocked by our security filters." }
```

### Other endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Component health check |
| `GET /metrics` | Requests, error rate, latency, cache hit rate |
| `GET /cache/stats` | Cache hits, misses and entries |

## Tests

```bash
uv run python -m tests.test_fix
```

18 checks covering injection attempts, normal messages, PII masking, and output validation.