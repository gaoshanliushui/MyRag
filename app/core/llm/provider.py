"""
LLM Provider - LangChain Facade

A thin business-level wrapper over LangChain chat models. The actual provider
implementation (Ollama / vLLM / OpenAI / mock) is selected via
`app.core.llm.factory.get_chat_model()`.

This module preserves the public method signatures that callers depend on
(`generate`, `stream_generate`, `count_tokens`) so existing code paths
(API endpoints, Celery tasks) keep working unchanged.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings
from app.core.llm.factory import get_chat_model
from app.utils.logging import get_logger

logger = get_logger("core.llm.provider")


class LLMProvider:
    """Business facade around LangChain chat models."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        # Parameters are accepted for backward compatibility; the chat model
        # singleton itself reads its config from settings via the factory.
        self.provider = provider or settings.LLM_PROVIDER
        self.model = model or settings.LLM_MODEL
        self.api_url = api_url or settings.LLM_API_URL
        self.api_key = api_key or settings.LLM_API_KEY
        logger.info(f"LLMProvider (LangChain facade) ready: {self.provider}/{self.model}")

    @property
    def _chat(self):
        return get_chat_model()

    async def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        stop_sequences: list[str] | None = None,
    ) -> tuple[str, str]:
        """Generate a single completion. Returns (text, model_used)."""
        chat = self._chat
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        bind_kwargs: dict = {}
        if max_tokens is not None:
            bind_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            bind_kwargs["temperature"] = temperature
        if stop_sequences:
            bind_kwargs["stop"] = stop_sequences

        model = chat.bind(**bind_kwargs) if bind_kwargs else chat
        try:
            result = await model.ainvoke(messages)
            text = result.content if hasattr(result, "content") else str(result)
            return text, self.model
        except Exception as exc:
            logger.error(f"LLM generation failed: {exc}")
            return (
                "[MOCK FALLBACK] LLM 调用失败，已回退到占位响应。请检查 LLM 配置。",
                "fallback",
            )

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream LLM output chunk by chunk."""
        chat = self._chat
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        bind_kwargs: dict = {}
        if max_tokens is not None:
            bind_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            bind_kwargs["temperature"] = temperature
        model = chat.bind(**bind_kwargs) if bind_kwargs else chat

        try:
            async for chunk in model.astream(messages):
                content = getattr(chunk, "content", None)
                if content:
                    yield content if isinstance(content, str) else str(content)
        except Exception as exc:
            logger.error(f"Streaming generation failed: {exc}")
            yield "[MOCK FALLBACK] 流式生成失败。"

    async def count_tokens(self, text: str) -> int:
        """Estimate token count (rough heuristic)."""
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
        non_chinese = len(text) - chinese_chars
        tokens = (chinese_chars // 2) + (non_chinese // 4)
        return max(1, tokens)

    async def close(self) -> None:
        """No-op kept for backward compatibility."""
        return None


def get_llm_provider() -> LLMProvider:
    """Return a new LLMProvider instance (cheap: delegates to the cached chat model)."""
    return LLMProvider()


__all__ = ["LLMProvider", "get_llm_provider"]


# Avoid leaking import side-effects when the module is loaded by tools.
_ = asyncio