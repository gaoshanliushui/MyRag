"""
LLM Provider - Configurable LLM integration

Supports multiple providers:
- Ollama: Local models via HTTP API
- vLLM: High-performance inference server
- OpenAI-compatible: Any API following OpenAI format
- Mock: For testing without real LLM
"""

import asyncio
import json
from typing import Any

import httpx

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger("core.llm.provider")


class LLMProvider:
    """
    Configurable LLM provider supporting multiple backends.

    Supports:
    - Ollama (localhost:11434)
    - vLLM (customizable URL)
    - OpenAI-compatible APIs
    - Mock (for testing)
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize LLM provider.

        Args:
            provider: Provider type (ollama, vllm, openai, mock)
            model: Model name
            api_url: API base URL
            api_key: API key (for OpenAI-compatible)
        """
        self.provider = provider or settings.LLM_PROVIDER
        self.model = model or settings.LLM_MODEL
        self.api_url = api_url or settings.LLM_API_URL
        self.api_key = api_key or settings.LLM_API_KEY

        # Client for HTTP requests
        self._client: httpx.AsyncClient | None = None

        logger.info(
            f"LLM Provider initialized: {self.provider}, model={self.model}"
        )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            timeout = httpx.Timeout(60.0, connect=10.0)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        stop_sequences: list[str] | None = None,
    ) -> tuple[str, str]:
        """
        Generate text from prompt.

        Args:
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            stop_sequences: Optional stop sequences

        Returns:
            (generated_text, model_used)
        """
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        temperature = temperature or settings.LLM_TEMPERATURE

        try:
            if self.provider == "ollama":
                return await self._generate_ollama(
                    prompt, max_tokens, temperature, system_prompt
                )
            elif self.provider == "vllm":
                return await self._generate_vllm(
                    prompt, max_tokens, temperature, system_prompt
                )
            elif self.provider == "openai":
                return await self._generate_openai(
                    prompt, max_tokens, temperature, system_prompt, stop_sequences
                )
            elif self.provider == "mock":
                return await self._generate_mock(prompt)
            else:
                logger.warning(f"Unknown provider: {self.provider}, using mock")
                return await self._generate_mock(prompt)

        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback to mock on error
            return await self._generate_mock(prompt)

    async def _generate_ollama(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str | None,
    ) -> tuple[str, str]:
        """Generate using Ollama API."""
        client = await self._get_client()

        # Build request
        data = {
            "model": self.model,
            "prompt": prompt,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
            "stream": False,
        }

        if system_prompt:
            data["system"] = system_prompt

        url = f"{self.api_url}/api/generate"

        logger.debug(f"Ollama request: {url}, model={self.model}")

        response = await client.post(url, json=data)
        response.raise_for_status()

        result = response.json()

        # Ollama returns response in "response" field
        generated = result.get("response", "")

        logger.debug(f"Ollama response: {len(generated)} chars")

        return generated, self.model

    async def _generate_vllm(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str | None,
    ) -> tuple[str, str]:
        """Generate using vLLM API (OpenAI-compatible)."""
        return await self._generate_openai(
            prompt, max_tokens, temperature, system_prompt
        )

    async def _generate_openai(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str | None,
        stop_sequences: list[str] | None = None,
    ) -> tuple[str, str]:
        """Generate using OpenAI-compatible API."""
        client = await self._get_client()

        # Build messages
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        # Build request
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if stop_sequences:
            data["stop"] = stop_sequences

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.api_url.rstrip('/')}/v1/chat/completions"

        logger.debug(f"OpenAI-compatible request: {url}, model={self.model}")

        response = await client.post(url, json=data, headers=headers)
        response.raise_for_status()

        result = response.json()

        # Extract generated text
        choices = result.get("choices", [])
        if not choices:
            logger.warning("No choices in OpenAI response")
            return "", self.model

        generated = choices[0].get("message", {}).get("content", "")

        logger.debug(f"OpenAI response: {len(generated)} chars")

        return generated, self.model

    async def _generate_mock(self, prompt: str) -> tuple[str, str]:
        """
        Generate mock response for testing.

        Returns a placeholder response indicating mock mode.
        """
        logger.warning("Using mock LLM provider - responses are placeholders")

        mock_response = (
            "[MOCK RESPONSE] This is a placeholder response from the mock LLM provider. "
            "To get real responses, configure a real LLM provider (ollama, vllm, or openai) "
            "in your environment variables.\n\n"
            f"Original prompt length: {len(prompt)} characters"
        )

        return mock_response, "mock-model"

    async def stream_generate(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ):
        """
        Generate text with streaming.

        Yields chunks as they are generated.

        Args:
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            system_prompt: Optional system prompt

        Yields:
            Text chunks
        """
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        temperature = temperature or settings.LLM_TEMPERATURE

        if self.provider == "mock":
            # Mock: yield all at once
            response, _ = await self._generate_mock(prompt)
            yield response
            return

        if self.provider not in ("ollama", "vllm", "openai"):
            logger.warning(f"Streaming not supported for provider: {self.provider}")
            response, _ = await self._generate_mock(prompt)
            yield response
            return

        try:
            client = await self._get_client()

            if self.provider == "ollama":
                async for chunk in self._stream_ollama(
                    client, prompt, max_tokens, temperature, system_prompt
                ):
                    yield chunk

            elif self.provider in ("vllm", "openai"):
                async for chunk in self._stream_openai(
                    client, prompt, max_tokens, temperature, system_prompt
                ):
                    yield chunk

        except Exception as e:
            logger.error(f"Streaming generation failed: {e}")
            # Fallback to mock
            response, _ = await self._generate_mock(prompt)
            yield response

    async def _stream_ollama(
        self,
        client: httpx.AsyncClient,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str | None,
    ):
        """Stream using Ollama API."""
        data = {
            "model": self.model,
            "prompt": prompt,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
            "stream": True,
        }

        if system_prompt:
            data["system"] = system_prompt

        url = f"{self.api_url}/api/generate"

        async with client.stream("POST", url, json=data) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue

                try:
                    chunk_data = json.loads(line)
                    chunk = chunk_data.get("response", "")
                    if chunk:
                        yield chunk

                    if chunk_data.get("done"):
                        break

                except json.JSONDecodeError:
                    continue

    async def _stream_openai(
        self,
        client: httpx.AsyncClient,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: str | None,
    ):
        """Stream using OpenAI-compatible API."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.api_url.rstrip('/')}/v1/chat/completions"

        async with client.stream("POST", url, json=data, headers=headers) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]  # Remove "data: " prefix

                if data_str.strip() == "[DONE]":
                    break

                try:
                    chunk_data = json.loads(data_str)
                    choices = chunk_data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        chunk = delta.get("content", "")
                        if chunk:
                            yield chunk

                except json.JSONDecodeError:
                    continue

    async def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        This is a rough estimation. For accurate counting,
        use tokenizer specific to the model.

        Args:
            text: Text to count tokens for

        Returns:
            Estimated token count
        """
        # Rough estimation: ~4 characters per token for Chinese
        # ~4 characters per token for English
        # This is not accurate but gives a ballpark

        # Count Chinese characters
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
        # Count non-Chinese characters
        non_chinese = len(text) - chinese_chars

        # Rough estimation
        tokens = (chinese_chars // 2) + (non_chinese // 4)

        return max(1, tokens)


def get_llm_provider() -> LLMProvider:
    """Get LLM provider instance."""
    return LLMProvider()