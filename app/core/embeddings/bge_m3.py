"""
BGE-M3 LangChain Embeddings

Implements the `langchain_core.embeddings.Embeddings` interface using the
BAAI/bge-m3 model via `langchain_huggingface.HuggingFaceEmbeddings`.

The Redis cache and async wrappers are kept in `app.utils.embeddings`.
This module is purely the LangChain-compatible embedder.
"""

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger("core.embeddings.bge_m3")


class BGE_M3_Embeddings(Embeddings):
    """BGE-M3 embedding model conforming to the LangChain `Embeddings` interface."""

    _instance: "BGE_M3_Embeddings | None" = None
    _inner: HuggingFaceEmbeddings | None = None

    def __new__(cls) -> "BGE_M3_Embeddings":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._inner is not None:
            return
        model_name = settings.EMBEDDING_MODEL_PATH or settings.EMBEDDING_MODEL
        logger.info(f"Loading BGE-M3 via HuggingFaceEmbeddings: {model_name}")
        self._inner = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": settings.EMBEDDING_DEVICE},
            encode_kwargs={
                "normalize_embeddings": True,
                "batch_size": settings.EMBEDDING_BATCH_SIZE,
            },
            multi_process=False,
        )

    @property
    def dimension(self) -> int:
        return settings.EMBEDDING_DIMENSION

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_documents(texts)  # type: ignore[union-attr]

    def embed_query(self, text: str) -> list[float]:
        return self._inner.embed_query(text)  # type: ignore[union-attr]

    def get_model_info(self) -> dict[str, Any]:
        return {
            "model": settings.EMBEDDING_MODEL,
            "dimension": self.dimension,
            "max_length": settings.EMBEDDING_MAX_LENGTH,
            "device": settings.EMBEDDING_DEVICE,
        }


_bge_m3_singleton: BGE_M3_Embeddings | None = None


def get_bge_m3() -> BGE_M3_Embeddings:
    """Return the BGE-M3 embeddings singleton."""
    global _bge_m3_singleton
    if _bge_m3_singleton is None:
        _bge_m3_singleton = BGE_M3_Embeddings()
    return _bge_m3_singleton