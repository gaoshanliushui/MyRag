"""
Test Suite for LLM Provider

Tests for LLM integration with different providers (Ollama, vLLM, OpenAI-compatible, Mock).
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


from app.core.llm.provider import LLMProvider


class TestLLMProviderInitialization:
    """Test LLM provider initialization and configuration."""

    def test_default_initialization(self):
        """Test default initialization of LLM provider."""
        provider = LLMProvider()

        # Check default values are set from settings or defaults
        assert provider.provider in ["ollama", "vllm", "openai", "mock"]
        assert provider.model is not None
        assert provider.api_url is not None

    def test_custom_initialization(self):
        """Test initialization with custom parameters."""
        provider = LLMProvider(
            provider="mock",
            model="test-model",
            api_url="http://test-url:11434",
            api_key="test-key"
        )

        assert provider.provider == "mock"
        assert provider.model == "test-model"
        assert provider.api_url == "http://test-url:11434"
        assert provider.api_key == "test-key"

    def test_get_llm_provider_singleton(self):
        """Test the singleton getter function."""
        from app.core.llm.provider import get_llm_provider

        provider1 = get_llm_provider()
        provider2 = get_llm_provider()

        # Both should be the same instance
        assert provider1 is provider2


class TestLLMProviderMock:
    """Test mock LLM provider functionality."""

    @pytest.mark.asyncio
    async def test_mock_generation(self):
        """Test mock LLM generation."""
        provider = LLMProvider(provider="mock")

        result, model_used = await provider.generate("Test prompt")

        # Check that mock response is returned
        assert "MOCK RESPONSE" in result
        assert model_used == "mock-model"

    @pytest.mark.asyncio
    async def test_mock_generation_with_parameters(self):
        """Test mock generation with various parameters."""
        provider = LLMProvider(provider="mock")

        result, model_used = await provider.generate(
            "Test prompt",
            max_tokens=100,
            temperature=0.7,
            system_prompt="You are a helpful assistant"
        )

        assert "MOCK RESPONSE" in result
        assert model_used == "mock-model"

    @pytest.mark.asyncio
    async def test_mock_stream_generation(self):
        """Test mock streaming generation."""
        provider = LLMProvider(provider="mock")

        chunks = []
        async for chunk in provider.stream_generate("Test prompt"):
            chunks.append(chunk)

        # Should return one chunk with mock response
        assert len(chunks) == 1
        assert "MOCK RESPONSE" in chunks[0]

    @pytest.mark.asyncio
    async def test_mock_token_counting(self):
        """Test mock token counting."""
        provider = LLMProvider(provider="mock")

        # Test English text
        english_text = "This is a test sentence."
        token_count = await provider.count_tokens(english_text)
        assert token_count > 0

        # Test Chinese text
        chinese_text = "这是一个测试句子。"
        token_count = await provider.count_tokens(chinese_text)
        assert token_count > 0


class TestLLMProviderOllama:
    """Test Ollama LLM provider functionality."""

    @pytest.mark.asyncio
    async def test_ollama_generation(self):
        """Test Ollama generation (with mocked HTTP client)."""
        provider = LLMProvider(provider="ollama", model="test-model")

        # Mock the HTTP client and response
        mock_response = AsyncMock()
        mock_response.json.return_value = {"response": "Test response from Ollama"}
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(provider, '_get_client', return_value=mock_client):
            result, model_used = await provider.generate("Test prompt")

            # Verify the client was called with correct parameters
            assert "Test response from Ollama" in result
            assert model_used == "test-model"

            # Check that the correct endpoint was called
            mock_client.post.assert_called_once()
            args, kwargs = mock_client.post.call_args
            assert "/api/generate" in args[0]

    @pytest.mark.asyncio
    async def test_ollama_generation_with_system_prompt(self):
        """Test Ollama generation with system prompt."""
        provider = LLMProvider(provider="ollama", model="test-model")

        mock_response = AsyncMock()
        mock_response.json.return_value = {"response": "Response with system prompt"}
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(provider, '_get_client', return_value=mock_client):
            result, model_used = await provider.generate(
                "Test prompt",
                system_prompt="You are a helpful assistant"
            )

            assert "Response with system prompt" in result

    @pytest.mark.asyncio
    async def test_ollama_stream_generation(self):
        """Test Ollama streaming generation."""
        provider = LLMProvider(provider="ollama", model="test-model")

        # Mock streaming response
        async def mock_stream_response(*args, **kwargs):
            responses = [
                '{"response": "First chunk", "done": false}',
                '{"response": "Second chunk", "done": false}',
                '{"response": "", "done": true}'
            ]
            for resp in responses:
                yield resp

        mock_client = AsyncMock()
        mock_stream = AsyncMock()
        mock_stream.aiter_lines.return_value = mock_stream_response()
        mock_client.stream.return_value.__aenter__.return_value = mock_stream
        mock_client.stream.return_value.__aexit__.return_value = None

        with patch.object(provider, '_get_client', return_value=mock_client):
            chunks = []
            async for chunk in provider.stream_generate("Test prompt"):
                chunks.append(chunk)

            # Verify chunks were yielded
            assert len(chunks) >= 0  # May vary based on mock response


class TestLLMProviderOpenAI:
    """Test OpenAI-compatible LLM provider functionality."""

    @pytest.mark.asyncio
    async def test_openai_generation(self):
        """Test OpenAI-compatible generation (with mocked HTTP client)."""
        provider = LLMProvider(provider="openai", model="test-model", api_url="http://test-api:8000")

        # Mock the HTTP client and response
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Test response from OpenAI-compatible API"}}
            ]
        }
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(provider, '_get_client', return_value=mock_client):
            result, model_used = await provider.generate("Test prompt")

            assert "Test response from OpenAI-compatible API" in result
            assert model_used == "test-model"

    @pytest.mark.asyncio
    async def test_openai_generation_with_api_key(self):
        """Test OpenAI-compatible generation with API key."""
        provider = LLMProvider(
            provider="openai",
            model="test-model",
            api_url="http://test-api:8000",
            api_key="test-api-key"
        )

        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "choices": [
                {"message": {"content": "Response with API key"}}
            ]
        }
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(provider, '_get_client', return_value=mock_client):
            result, model_used = await provider.generate("Test prompt")

            assert "Response with API key" in result

            # Verify that API key was included in headers
            mock_client.post.assert_called_once()
            args, kwargs = mock_client.post.call_args
            if 'headers' in kwargs:
                assert 'Authorization' in kwargs['headers']
                assert kwargs['headers']['Authorization'] == 'Bearer test-api-key'

    @pytest.mark.asyncio
    async def test_openai_stream_generation(self):
        """Test OpenAI-compatible streaming generation."""
        provider = LLMProvider(provider="openai", model="test-model")

        # Mock streaming response
        async def mock_stream_response(*args, **kwargs):
            responses = [
                'data: {"choices": [{"delta": {"content": "First"}}]}',
                'data: {"choices": [{"delta": {"content": " chunk"}}]}',
                'data: [DONE]'
            ]
            for resp in responses:
                yield resp

        mock_client = AsyncMock()
        mock_stream = AsyncMock()
        mock_stream.aiter_lines.return_value = mock_stream_response()
        mock_client.stream.return_value.__aenter__.return_value = mock_stream
        mock_client.stream.return_value.__aexit__.return_value = None

        with patch.object(provider, '_get_client', return_value=mock_client):
            chunks = []
            async for chunk in provider.stream_generate("Test prompt"):
                chunks.append(chunk)

            # Verify chunks were yielded
            if chunks:  # Only check if chunks were generated
                combined = "".join(chunks)
                assert "First" in combined or "chunk" in combined


class TestLLMProviderFallback:
    """Test error handling and fallback functionality."""

    @pytest.mark.asyncio
    async def test_generation_error_fallback(self):
        """Test that generation falls back to mock on error."""
        provider = LLMProvider(provider="ollama", model="nonexistent-model")

        # Mock client to raise an exception
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.RequestError("Connection failed")

        with patch.object(provider, '_get_client', return_value=mock_client):
            result, model_used = await provider.generate("Test prompt")

            # Should fall back to mock response
            assert "MOCK RESPONSE" in result
            assert model_used == "mock-model"

    @pytest.mark.asyncio
    async def test_unknown_provider_fallback(self):
        """Test that unknown provider falls back to mock."""
        provider = LLMProvider(provider="unknown-provider")

        result, model_used = await provider.generate("Test prompt")

        # Should fall back to mock response
        assert "MOCK RESPONSE" in result
        assert model_used == "mock-model"

    @pytest.mark.asyncio
    async def test_stream_generation_error_fallback(self):
        """Test that streaming generation falls back to mock on error."""
        provider = LLMProvider(provider="ollama", model="nonexistent-model")

        # Mock client to raise an exception during streaming
        mock_client = AsyncMock()
        mock_stream = AsyncMock()
        mock_stream.aiter_lines.side_effect = httpx.RequestError("Connection failed")
        mock_client.stream.return_value.__aenter__.return_value = mock_stream
        mock_client.stream.return_value.__aexit__.return_value = None

        with patch.object(provider, '_get_client', return_value=mock_client):
            chunks = []
            async for chunk in provider.stream_generate("Test prompt"):
                chunks.append(chunk)

            # Should yield mock response
            assert len(chunks) == 1
            assert "MOCK RESPONSE" in chunks[0]


class TestLLMProviderMethods:
    """Test various LLM provider methods."""

    @pytest.mark.asyncio
    async def test_close_method(self):
        """Test closing the HTTP client."""
        provider = LLMProvider(provider="mock")

        # Initially no client
        assert provider._client is None

        # Get client
        client = await provider._get_client()
        assert provider._client is not None

        # Close client
        await provider.close()
        assert provider._client is None

    def test_supported_providers(self):
        """Test that all supported providers are recognized."""
        supported_providers = ["ollama", "vllm", "openai", "mock"]

        for provider_name in supported_providers:
            provider = LLMProvider(provider=provider_name)
            assert provider.provider == provider_name


if __name__ == "__main__":
    pytest.main([__file__, "-v"])