from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.logger import get_logger
from app.lg_agent.pipeline import run_commerce_agent


logger = get_logger(service="agent_api")
router = APIRouter(prefix="/agent", tags=["commerce-agent"])


class AgentQueryRequest(BaseModel):
    query: str = ""
    user_id: int = 1
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    messages: List[Dict[str, str]] = Field(default_factory=list)


class AgentQueryResponse(BaseModel):
    answer: str
    recommendations: List[Dict[str, Any]]
    retrieval_candidates: List[Dict[str, Any]]
    agent_trace: List[Dict[str, Any]]
    metadata: Dict[str, Any]


@router.post("/query", response_model=AgentQueryResponse)
async def query_agent(request: AgentQueryRequest):
    query = request.query.strip() or _last_user_message(request.messages)
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    try:
        logger.info(f"Commerce agent query: user={request.user_id}, query={query[:80]}")
        return await run_commerce_agent(
            query,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            messages=request.messages or [{"role": "user", "content": query}],
            session_id=request.session_id,
        )
    except Exception as exc:
        logger.error(f"Commerce agent query failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/query/stream")
async def query_agent_stream(request: AgentQueryRequest):
    """SSE stage-level streaming endpoint.

    Returns ``text/event-stream`` with ``stage`` events for each pipeline
    step and a ``final`` event carrying the full response.
    """
    query = request.query.strip() or _last_user_message(request.messages)
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    queue: asyncio.Queue[str] = asyncio.Queue()

    async def _event_sink(event: str) -> None:
        await queue.put(event)

    async def _run_pipeline() -> None:
        try:
            await run_commerce_agent(
                query,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                messages=request.messages or [{"role": "user", "content": query}],
                event_sink=_event_sink,
                session_id=request.session_id,
            )
        except Exception as exc:
            logger.error(f"Stream pipeline failed: {exc}", exc_info=True)
            await queue.put(
                'data: {"type": "error", "message": "' + str(exc)[:200].replace('"', "'") + '"}\n\n'
            )
        finally:
            await queue.put(None)  # sentinel

    async def _stream() -> AsyncGenerator[str, None]:
        task = asyncio.create_task(_run_pipeline())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            await task

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _last_user_message(messages: List[Dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user" and message.get("content"):
            return str(message["content"]).strip()
    return ""
