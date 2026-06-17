"""
BGE-M3 Embedding Service

Provides:
- Dense embeddings for semantic similarity
- Batch inference for efficiency
- GPU/CPU device selection
- Redis caching for embeddings
"""

import hashlib
import asyncio
from typing import Any

from sentence_transformers import SentenceTransformer

from app.config import settings
from app.core.monitoring.metrics import record_cache_metrics
from app.utils.exceptions import EmbeddingError
from app.utils.logging import get_logger

logger = get_logger("utils.embeddings")


class EmbeddingService:
    """
    BGE-M3 embedding service with caching.

    BGE-M3 supports:
    - Dense retrieval (1024 dimensions)
    - Sparse retrieval (lexical)
    - ColBERT (multi-vector)
    """

    _instance: "EmbeddingService | None" = None
    _model: SentenceTransformer | None = None

    def __new__(cls) -> "EmbeddingService":
        """Singleton pattern for model reuse."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize embedding model."""
        if self._model is None:
            self._load_model()

    def _load_model(self) -> None:
        """Load BGE-M3 model."""
        model_name_or_path = (
            settings.EMBEDDING_MODEL_PATH
            or settings.EMBEDDING_MODEL
        )

        logger.info(f"Loading embedding model: {model_name_or_path}")
        logger.info(f"Device: {settings.EMBEDDING_DEVICE}")

        try:
            self._model = SentenceTransformer(
                model_name_or_path,
                device=settings.EMBEDDING_DEVICE,
            )

            # Model info
            self._dimension = settings.EMBEDDING_DIMENSION
            self._max_length = settings.EMBEDDING_MAX_LENGTH

            logger.info(
                f"Model loaded: dimension={self._dimension}, "
                f"max_length={self._max_length}"
            )

        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise EmbeddingError("", f"Model loading failed: {e}")

    def _get_text_hash(self, text: str) -> str:
        """Generate hash for text caching."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _check_cache(
        self,
        tenant_id: str,
        text_hash: str,
    ) -> list[float] | None:
        """Check Redis cache for embedding."""
        from app.db.redis import get_redis_client

        redis = await get_redis_client()
        cached = await redis.get_vector_cache(tenant_id, text_hash)

        if cached:
            record_cache_metrics(tenant_id, "vector", hit=True)
            return cached

        record_cache_metrics(tenant_id, "vector", hit=False)
        return None

    async def _cache_embedding(
        self,
        tenant_id: str,
        text_hash: str,
        embedding: list[float],
    ) -> None:
        """Cache embedding in Redis."""
        from app.db.redis import get_redis_client

        redis = await get_redis_client()
        await redis.set_vector_cache(tenant_id, text_hash, embedding)

    def encode_single(self, text: str) -> list[float]:
        """
        Encode single text to embedding.

        Args:
            text: Input text

        Returns:
            Dense embedding vector (list of floats)
        """
        if self._model is None:
            raise EmbeddingError(text, "Model not loaded")

        # Truncate if too long
        if len(text) > self._max_length:
            logger.warning(f"Text truncated from {len(text)} to {self._max_length}")
            text = text[:self._max_length]

        try:
            embedding = self._model.encode(
                text,
                normalize_embeddings=True,  # For cosine similarity
                show_progress_bar=False,
            )
            return embedding.tolist()

        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise EmbeddingError(text, str(e))

    def encode_batch(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> list[list[float]]:
        """
        Encode batch of texts.

        Args:
            texts: List of input texts
            batch_size: Batch size for encoding

        Returns:
            List of embedding vectors
        """
        if self._model is None:
            raise EmbeddingError("", "Model not loaded")

        batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE

        # Truncate texts
        truncated = [
            t[:self._max_length] if len(t) > self._max_length else t
            for t in texts
        ]

        try:
            embeddings = self._model.encode(
                truncated,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return [e.tolist() for e in embeddings]

        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise EmbeddingError("", str(e))

    async def encode_single_async(
        self,
        text: str,
        tenant_id: str | None = None,
        use_cache: bool = True,
    ) -> list[float]:
        """
        Async single embedding with optional caching.

        Args:
            text: Input text
            tenant_id: Tenant for cache isolation
            use_cache: Whether to use Redis cache

        Returns:
            Embedding vector
        """
        # Check cache
        if use_cache and tenant_id:
            text_hash = self._get_text_hash(text)
            cached = await self._check_cache(tenant_id, text_hash)
            if cached:
                logger.debug(f"Embedding cache hit for tenant {tenant_id}")
                return cached

        # Encode (run in thread pool to avoid blocking)
        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(None, self.encode_single, text)

        # Cache result
        if use_cache and tenant_id:
            text_hash = self._get_text_hash(text)
            await self._cache_embedding(tenant_id, text_hash, embedding)

        return embedding

    async def encode_batch_async(
        self,
        texts: list[str],
        tenant_id: str | None = None,
        use_cache: bool = True,
    ) -> list[list[float]]:
        """
        Async batch embedding with optional caching.

        Args:
            texts: List of texts
            tenant_id: Tenant for cache isolation
            use_cache: Whether to use Redis cache

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Check cache for each text
        if use_cache and tenant_id:
            results: list[list[float] | None] = []
            uncached_indices: list[int] = []
            uncached_texts: list[str] = []

            for i, text in enumerate(texts):
                text_hash = self._get_text_hash(text)
                cached = await self._check_cache(tenant_id, text_hash)
                if cached:
                    results.append(cached)
                else:
                    results.append(None)
                    uncached_indices.append(i)
                    uncached_texts.append(text)

            # Encode uncached texts
            if uncached_texts:
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None,
                    self.encode_batch,
                    uncached_texts,
                )

                # Fill results and cache
                for idx, embedding in zip(uncached_indices, embeddings):
                    results[idx] = embedding
                    text_hash = self._get_text_hash(uncached_texts[idx])
                    await self._cache_embedding(tenant_id, text_hash, embedding)

            return results

        # No caching - just encode
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.encode_batch, texts)

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        return self._dimension

    def get_model_info(self) -> dict[str, Any]:
        """Get model information."""
        return {
            "model": settings.EMBEDDING_MODEL,
            "dimension": self._dimension,
            "max_length": self._max_length,
            "device": settings.EMBEDDING_DEVICE,
        }


# Singleton accessor
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service