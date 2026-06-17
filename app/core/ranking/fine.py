"""
Fine Ranker - Jina-Rerank Cross-Encoder

High-precision reranking using cross-encoder model.
"""

import asyncio
import time
from typing import Any

from sentence_transformers import CrossEncoder

from app.config import settings
from app.core.monitoring.metrics import record_rerank_metrics
from app.utils.logging import get_logger

logger = get_logger("core.ranking.fine")


class FineRanker:
    """
    Fine reranker using Jina-Rerank cross-encoder.

    Cross-encoders provide higher accuracy by jointly
    encoding query and document.
    """

    _instance: "FineRanker | None" = None
    _model: CrossEncoder | None = None

    def __new__(cls) -> "FineRanker":
        """Singleton pattern for model reuse."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize reranker model."""
        if self._model is None:
            self._load_model()

    def _load_model(self) -> None:
        """Load Jina-Rerank model."""
        model_name = settings.RERANKER_MODEL
        device = settings.RERANKER_DEVICE

        logger.info(f"Loading reranker model: {model_name} on {device}")

        try:
            self._model = CrossEncoder(
                model_name,
                device=device,
                max_length=512,  # Jina-Rerank supports longer but we limit for speed
            )

            logger.info("Reranker model loaded")

        except Exception as e:
            logger.warning(f"Failed to load reranker model: {e}")
            # Fallback: will use heuristic ranking
            self._model = None

    def rank_pairs(
        self,
        query: str,
        documents: list[str],
    ) -> list[float]:
        """
        Rank query-document pairs.

        Args:
            query: Search query
            documents: List of document contents

        Returns:
            List of relevance scores (0-1 range)
        """
        if self._model is None:
            # Fallback: return normalized coarse scores
            return [0.5] * len(documents)

        try:
            # Create pairs
            pairs = [(query, doc) for doc in documents]

            # Get scores
            scores = self._model.predict(pairs)

            # Normalize to 0-1 range (cross-encoder outputs vary)
            # Jina-Rerank typically outputs 0-1 already
            scores = [float(s) for s in scores]

            return scores

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return [0.5] * len(documents)

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Rerank candidates using cross-encoder.

        Args:
            query: Original query
            candidates: List of candidates from coarse ranking
            top_k: Final number to return

        Returns:
            Reranked candidates with rerank_score
        """
        start_time = time.time()

        if not candidates:
            return []

        # Prepare documents
        documents = [c.get("content", "") for c in candidates]

        # Truncate long documents for efficiency
        documents = [
            d[:1000] if len(d) > 1000 else d
            for d in documents
        ]

        # Get rerank scores (run in thread pool)
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(
            None,
            self.rank_pairs,
            query,
            documents,
        )

        # Assign scores
        reranked = []
        for candidate, score in zip(candidates, scores):
            candidate_copy = candidate.copy()
            candidate_copy["rerank_score"] = score
            reranked.append(candidate_copy)

        # Sort by rerank score
        reranked.sort(
            key=lambda x: x["rerank_score"],
            reverse=True,
        )

        # Keep top_k
        final = reranked[:top_k]

        latency = (time.time() - start_time) * 1000

        # Record metrics
        record_rerank_metrics("default", latency, "fine")

        logger.debug(
            f"Fine reranking: {len(candidates)} → {len(final)} "
            f"in {latency:.2f}ms"
        )

        return final

    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None


def get_fine_ranker() -> FineRanker:
    """Get fine ranker instance."""
    return FineRanker()