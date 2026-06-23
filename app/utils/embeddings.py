"""
Embedding Service (LangChain facade)

Provides async embedding APIs with Redis caching, tenant isolation, and
batch inference. Internally delegates to `app.core.embeddings.bge_m3`,
which wraps the BGE-M3 model via LangChain's `HuggingFaceEmbeddings`.

Public method signatures are preserved so existing callers
(API endpoints, Celery tasks, retrievers) need no changes.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from app.config import settings
from app.core.embeddings.bge_m3 import get_bge_m3
from app.core.monitoring.metrics import record_cache_metrics
from app.utils.exceptions import EmbeddingError
from app.utils.logging import get_logger

logger = get_logger("utils.embeddings")


class EmbeddingService:
    """Async embedding service backed by LangChain's `BGE_M3_Embeddings`."""

    _instance: "EmbeddingService | None" = None

    def __new__(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        # Underlying LangChain embedder (lazy-loaded on first encode)
        self._bge = get_bge_m3()
        self._dimension = settings.EMBEDDING_DIMENSION
        self._max_length = settings.EMBEDDING_MAX_LENGTH

    # --- internal helpers -------------------------------------------------

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _check_cache(self, tenant_id: str, text_hash: str) -> list[float] | None:
        try:
            from app.db.redis import get_redis_client

            redis = await get_redis_client()
            cached = await redis.get_vector_cache(tenant_id, text_hash)
        except Exception as exc:  # pragma: no cover - cache failures are non-fatal
            logger.debug(f"Redis vector cache read failed: {exc}")
            return None
        record_cache_metrics(tenant_id, "vector", hit=bool(cached))
        return cached

    async def _write_cache(
        self, tenant_id: str, text_hash: str, embedding: list[float]
    ) -> None:
        try:
            from app.db.redis import get_redis_client

            redis = await get_redis_client()
            await redis.set_vector_cache(tenant_id, text_hash, embedding)
        except Exception as exc:  # pragma: no cover
            logger.debug(f"Redis vector cache write failed: {exc}")

    def _truncate(self, text: str) -> str:
        if len(text) > self._max_length:
            logger.warning(f"Text truncated from {len(text)} to {self._max_length}")
            return text[: self._max_length]
        return text

    # --- sync paths (kept for direct callers) -----------------------------

    def encode_single(self, text: str) -> list[float]:
        text = self._truncate(text)
        try:
            return self._bge.embed_query(text)
        except Exception as exc:
            logger.error(f"Embedding failed: {exc}")
            raise EmbeddingError(text, str(exc))

    def encode_batch(
        self, texts: list[str], batch_size: int | None = None
    ) -> list[list[float]]:
        truncated = [self._truncate(t) for t in texts]
        try:
            return self._bge.embed_documents(truncated)
        except Exception as exc:
            logger.error(f"Batch embedding failed: {exc}")
            raise EmbeddingError("", str(exc))

    # --- async paths (used by API + tasks + retrievers) -------------------

    async def encode_single_async(
        self,
        text: str,
        tenant_id: str | None = None,
        use_cache: bool = True,
    ) -> list[float]:
        if use_cache and tenant_id:
            text_hash = self._hash(text)
            cached = await self._check_cache(tenant_id, text_hash)
            if cached:
                return cached

        loop = asyncio.get_event_loop()
        embedding = await loop.run_in_executor(None, self.encode_single, text)

        if use_cache and tenant_id:
            await self._write_cache(tenant_id, self._hash(text), embedding)
        return embedding

    async def encode_batch_async(
        self,
        texts: list[str],
        tenant_id: str | None = None,
        use_cache: bool = True,
    ) -> list[list[float]]:
        if not texts:
            return []
        if use_cache and tenant_id:
            results: list[list[float] | None] = []
            uncached_indices: list[int] = []
            uncached_texts: list[str] = []
            for i, t in enumerate(texts):
                h = self._hash(t)
                cached = await self._check_cache(tenant_id, h)
                if cached:
                    results.append(cached)
                else:
                    results.append(None)
                    uncached_indices.append(i)
                    uncached_texts.append(t)

            if uncached_texts:
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None, self.encode_batch, uncached_texts
                )
                for idx, emb in zip(uncached_indices, embeddings):
                    results[idx] = emb
                    await self._write_cache(
                        tenant_id, self._hash(uncached_texts[idx]), emb
                    )
            return results  # type: ignore[return-value]

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.encode_batch, texts)

    # --- introspection ----------------------------------------------------

    def get_dimension(self) -> int:
        return self._dimension

    def get_model_info(self) -> dict[str, Any]:
        return {
            "model": settings.EMBEDDING_MODEL,
            "dimension": self._dimension,
            "max_length": self._max_length,
            "device": settings.EMBEDDING_DEVICE,
            "backend": "langchain-huggingface",
        }


# Singleton accessor
_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Return the embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


__all__ = ["EmbeddingService", "get_embedding_service"]