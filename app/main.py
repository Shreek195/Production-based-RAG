"""
Production-Ready FastAPI + LangGraph Application

Wires together:
- Security pipeline (input sanitization, PII masking)
- Response caching
- Rate limiting (slowapi)
- LangGraph agent (with retries + fallback)
- Structured logging + metrics
- LangSmith tracing
- Health checks
"""

import time
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from langsmith import traceable
from dotenv import load_dotenv

from app.config import get_settings
from app.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    MetricsResponse,
    ErrorResponse,
)

from app.security import SecurityPipeline
from app.cache import ResponseCache
from app.monitoring import get_logger, MetricsCollector, RequestTimer
from app.agent import ProductionAgent

load_dotenv()
logger = get_logger("production-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize all components on startup, clean up on shutdown.
    """
    settings = get_settings()

    logger.info(
        "Starting production API...",
        extra={
            "extra_data": {
                "environment": settings.app_env,
                "primary_model": settings.primary_model,
                "tracing_enabled": settings.langchain_tracing_v2,
            }
        },
    )

    # Attach components to app.state instead of using globals
    app.state.security = SecurityPipeline()
    app.state.cache = ResponseCache(ttl_seconds=settings.cache_ttl_seconds)
    app.state.metrics = MetricsCollector()
    app.state.agent = ProductionAgent()

    logger.info("All components initialized. Ready to serve requests.")

    yield  # App is running

    # Shutdown
    logger.info("Shutting down...", extra={"extra_data": app.state.metrics.summary})


# Rate Limiter Setup
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Production LangGraph API",
    description="A production-ready chat API with security, caching, and observability.",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter


# Exception Handlers
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(
        "Rate limit exceeded", extra={"extra_data": {"ip": get_remote_address(request)}}
    )
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded. Please try again later.",
            "detail": "Too many requests. Please slow down.",
        },
    )


# Endpoints
@app.post("/chat", response_model=ChatResponse)
@limiter.limit(get_settings().rate_limit)
@traceable(name="chat_endpoint")
async def chat(request: Request, body: ChatRequest):
    # Access components from app.state
    security = request.app.state.security
    cache = request.app.state.cache
    metrics = request.app.state.metrics
    agent = request.app.state.agent

    with RequestTimer() as timer:
        security_notes = []

        # Step 1: Security Check
        is_allowed, cleaned_message, notes = security.check_input(body.message)

        # Ensure notes is a list before extending, or just append if it's a string
        if isinstance(notes, list):
            security_notes.extend(notes)
        elif notes:
            security_notes.append(notes)

        if not is_allowed:
            logger.warning(
                "Request blocked by security", extra={"extra_data": {"reason": notes}}
            )

            # FIXED: Added required missing token arguments
            metrics.record_request(
                latency_ms=0, input_tokens=0, output_tokens=0, error=True
            )
            raise HTTPException(
                status_code=400,
                detail="Your message was blocked by our security filters.",
            )

        # Step 2: Cache Lookup
        cached_response = cache.get(cleaned_message)
        if cached_response is not None:
            # FIXED: Added required missing token arguments
            metrics.record_request(
                latency_ms=0, input_tokens=0, output_tokens=0, cache_hit=True
            )
            logger.info(
                "Cache hit", extra={"extra_data": {"thread_id": body.thread_id}}
            )

            return ChatResponse(
                response=cached_response,
                thread_id=body.thread_id,
                model_used="cache",
                cached=True,
                processing_time_ms=0,
                security_notes=security_notes,
            )

        # Step 3: Invoke LangGraph Agent
        try:
            # FIXED: Pushed the synchronous LLM call to a background thread
            result = await asyncio.to_thread(agent.invoke, cleaned_message)
        except Exception as e:
            logger.error(f"Agent invocation failed: {e}")
            metrics.record_request(
                latency_ms=0, input_tokens=0, output_tokens=0, error=True
            )
            raise HTTPException(
                status_code=500,
                detail="An error occurred while processing your request.",
            )

        response_text = result["response"]
        model_used = result["model_used"]

        # Step 4: Output Validation
        validated_response, output_warnings = security.check_output(response_text)

        if isinstance(output_warnings, list):
            security_notes.extend(output_warnings)
        elif output_warnings:
            security_notes.append(output_warnings)

        # Step 5: Cache Store
        cache.set(cleaned_message, validated_response)

    # Step 6: Log & Record Metrics
    input_tokens = int(len(cleaned_message.split()) * 1.3)
    output_tokens = int(len(validated_response.split()) * 1.3)

    metrics.record_request(
        latency_ms=timer.elapsed_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_hit=False,
    )

    return ChatResponse(
        response=validated_response,
        thread_id=body.thread_id,
        model_used=model_used,
        cached=False,
        processing_time_ms=round(timer.elapsed_ms, 2),
        security_notes=security_notes,
    )


@app.get("/health", response_model=HealthResponse)
async def health(request: Request):
    settings = get_settings()

    checks = {
        "agent": hasattr(request.app.state, "agent"),
        "security": hasattr(request.app.state, "security"),
        "cache": hasattr(request.app.state, "cache"),
    }

    all_healthy = all(checks.values())

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        environment=settings.app_env,
        checks=checks,
    )


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics(request: Request):
    summary = request.app.state.metrics.summary
    return MetricsResponse(**summary)


@app.get("/cache/stats")
async def cache_stats(request: Request):
    return request.app.state.cache.stats
