"""
ChatModel Factory

Unified LangChain chat model factory. Returns a `BaseChatModel` according to
`LLM_PROVIDER` setting (ollama / vllm / openai / mock).

This is the single entry point for all LLM interactions in the project.
"""

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger("core.llm.factory")


@lru_cache
def get_chat_model() -> BaseChatModel:
    """
    Return a LangChain `BaseChatModel` based on the configured provider.

    Supports:
    - mock: FakeListChatModel (no real LLM)
    - ollama: ChatOllama via init_chat_model
    - vllm / openai: ChatOpenAI-compatible endpoint
    """
    provider = settings.LLM_PROVIDER
    model = settings.LLM_MODEL
    api_url = settings.LLM_API_URL
    api_key = settings.LLM_API_KEY
    temperature = settings.LLM_TEMPERATURE
    max_tokens = settings.LLM_MAX_TOKENS

    logger.info(f"Creating chat model: provider={provider}, model={model}")

    if provider == "mock":
        return FakeListChatModel(
            responses=[
                "[MOCK] 暂无 LLM 服务；请在环境变量中配置 LLM_PROVIDER。",
            ]
        )

    if provider == "ollama":
        return init_chat_model(
            model,
            model_provider="ollama",
            base_url=api_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    if provider in ("openai", "vllm"):
        return init_chat_model(
            model,
            model_provider="openai",
            api_key=api_key or "EMPTY",
            base_url=api_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def reset_chat_model_cache() -> None:
    """Clear cached chat model (useful for tests / config reload)."""
    get_chat_model.cache_clear()