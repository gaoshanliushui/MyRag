"""
Confidence Scorer

Compute retrieval confidence for hallucination suppression.
"""

import time
from typing import Any

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger("core.ranking.confidence")


class ConfidenceScorer:
    """
    Compute confidence scores for retrieved chunks.

    Factors:
    - Rerank score quality
    - Source authority
    - Cross-corroboration (multiple sources agree)
    - Chunk coherence (self-contained)
    """

    def __init__(
        self,
        threshold: float = None,
    ):
        self.threshold = threshold or settings.CONFIDENCE_THRESHOLD

    def score_confidence(
        self,
        candidate: dict[str, Any],
    ) -> float:
        """
        Compute confidence score for a single candidate.

        Args:
            candidate: Retrieved candidate with scores

        Returns:
            Confidence score (0-1)
        """
        # Base: rerank score (most reliable)
        rerank_score = candidate.get("rerank_score", 0)
        if rerank_score is None:
            rerank_score = candidate.get("fusion_score", 0) or 0

        # Normalize to 0-1
        base_confidence = min(max(rerank_score, 0), 1)

        # Factor 1: Score consistency (dense vs sparse agreement)
        dense_score = candidate.get("dense_score")
        sparse_score = candidate.get("sparse_score")

        score_consistency = 0.5  # Default
        if dense_score is not None and sparse_score is not None:
            # Both retrieved = higher confidence
            if dense_score > 0.5 and sparse_score > 5:
                score_consistency = 0.8
            elif dense_score > 0.3 or sparse_score > 3:
                score_consistency = 0.6
            else:
                score_consistency = 0.4

        # Factor 2: Chunk quality (length, completeness)
        content = candidate.get("content", "")
        content_length = len(content)

        if content_length > 200:
            chunk_quality = 0.7
        elif content_length > 50:
            chunk_quality = 0.5
        else:
            chunk_quality = 0.3

        # Factor 3: Has source page (traceability)
        has_page = candidate.get("page_number") is not None
        traceability = 0.8 if has_page else 0.6

        # Combine factors
        confidence = (
            0.4 * base_confidence +
            0.2 * score_consistency +
            0.2 * chunk_quality +
            0.2 * traceability
        )

        return confidence

    def score_batch(
        self,
        candidates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Score confidence for a batch of candidates.

        Args:
            candidates: List of candidates

        Returns:
            Candidates with confidence scores
        """
        scored = []

        for candidate in candidates:
            confidence = self.score_confidence(candidate)
            candidate_copy = candidate.copy()
            candidate_copy["confidence"] = confidence
            scored.append(candidate_copy)

        return scored

    def filter_low_confidence(
        self,
        candidates: list[dict[str, Any]],
        threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Filter out low-confidence candidates.

        Args:
            candidates: Scored candidates
            threshold: Confidence threshold

        Returns:
            High-confidence candidates
        """
        threshold = threshold or self.threshold

        filtered = [
            c for c in candidates
            if c.get("confidence", 0) >= threshold
        ]

        logger.debug(
            f"Confidence filter: {len(candidates)} → {len(filtered)} "
            f"(threshold={threshold})"
        )

        return filtered

    def get_aggregate_confidence(
        self,
        candidates: list[dict[str, Any]],
    ) -> float:
        """
        Compute aggregate confidence for answer generation.

        Higher when multiple high-confidence sources agree.

        Args:
            candidates: All retrieved candidates

        Returns:
            Aggregate confidence (0-1)
        """
        if not candidates:
            return 0.0

        # Get individual confidences
        confidences = [c.get("confidence", 0) for c in candidates]

        # Weight by position (top candidates matter more)
        weights = [1.0 / (i + 1) for i in range(len(confidences))]

        # Weighted average
        total_weight = sum(weights)
        weighted_sum = sum(c * w for c, w in zip(confidences, weights))

        aggregate = weighted_sum / total_weight if total_weight > 0 else 0.0

        # Boost if multiple high-confidence sources
        high_confidence_count = sum(1 for c in confidences if c >= 0.7)
        if high_confidence_count >= 3:
            aggregate = min(aggregate + 0.1, 1.0)

        return aggregate


def get_confidence_scorer() -> ConfidenceScorer:
    """Get confidence scorer instance."""
    return ConfidenceScorer()