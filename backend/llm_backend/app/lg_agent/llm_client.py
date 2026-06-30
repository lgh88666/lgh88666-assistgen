"""Small LLM helper for the commerce agent slice."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.config import ServiceType, settings
from app.core.logger import get_logger

logger = get_logger(service="commerce_llm")


async def generate_text(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: Optional[int] = None,
    tags: Optional[List[str]] = None,
) -> str:
    """Generate one non-streaming LLM response.

    Agent nodes should call this helper instead of constructing model clients
    directly. If the configured LLM fails, callers can catch the exception and
    fall back to deterministic behavior.
    """

    model = _create_model(temperature=temperature, max_tokens=max_tokens, tags=tags or [])
    response = await model.ainvoke(messages)
    return str(getattr(response, "content", response) or "").strip()


def _create_model(*, temperature: float, max_tokens: Optional[int], tags: List[str]) -> Any:
    if settings.AGENT_SERVICE == ServiceType.OLLAMA:
        from langchain_ollama import ChatOllama

        kwargs: Dict[str, Any] = {
            "model": settings.OLLAMA_AGENT_MODEL,
            "base_url": settings.OLLAMA_BASE_URL,
            "temperature": temperature,
            "tags": tags,
        }
        if max_tokens:
            kwargs["num_predict"] = max_tokens
        return ChatOllama(**kwargs)

    from langchain_deepseek import ChatDeepSeek

    kwargs = {
        "api_key": settings.DEEPSEEK_API_KEY,
        "api_base": settings.DEEPSEEK_BASE_URL,
        "model_name": settings.DEEPSEEK_MODEL,
        "temperature": temperature,
        "tags": tags,
    }
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    return ChatDeepSeek(**kwargs)


def llm_config_label() -> str:
    if settings.AGENT_SERVICE == ServiceType.OLLAMA:
        return f"Ollama / {settings.OLLAMA_AGENT_MODEL}"
    return f"DeepSeek / {settings.DEEPSEEK_MODEL}"
