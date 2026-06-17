"""
Coarse Ranker - Lightweight Fast Ranking

Fast heuristic-based ranking for initial filtering.
Uses: TF-IDF similarity, entity overlap, recency, source authority.
"""

import math
import re
import time
from collections import Counter
from typing import Any

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger("core.ranking.coarse")


class CoarseRanker:
    """
    Lightweight coarse ranker.

    Features:
    - TF-IDF similarity (fast)
    - Entity overlap
    - Recency weighting
    - Source authority (document access count)
    """

    def __init__(self):
        self._idf_cache: dict[str, float] = {}
        self._document_stats: dict[str, dict] = {}

    def compute_tfidf_similarity(
        self,
        query: str,
        content: str,
    ) -> float:
        """
        Compute TF-IDF similarity between query and content.

        Simplified TF-IDF for fast computation.
        """
        # Tokenize
        query_tokens = self._tokenize(query)
        content_tokens = self._tokenize(content)

        if not query_tokens or not content_tokens:
            return 0.0

        # Compute TF for query
        query_tf = Counter(query_tokens)

        # Compute TF-IDF for content
        content_tf = Counter(content_tokens)

        # Compute cosine similarity using TF
        dot_product = sum(
            query_tf.get(token, 0) * content_tf.get(token, 0)
            for token in set(query_tokens) | set(content_tokens)
        )

        query_norm = math.sqrt(sum(v ** 2 for v in query_tf.values()))
        content_norm = math.sqrt(sum(v ** 2 for v in content_tf.values()))

        if query_norm == 0 or content_norm == 0:
            return 0.0

        return dot_product / (query_norm * content_norm)

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization."""
        # Lowercase and split
        text = text.lower()

        # Split by whitespace and punctuation
        tokens = re.findall(r"\b\w+\b", text)

        # Filter short tokens
        tokens = [t for t in tokens if len(t) > 1]

        return tokens

    def compute_entity_overlap(
        self,
        query: str,
        content: str,
    ) -> float:
        """
        Compute entity overlap ratio.

        Extracts entities and measures overlap.
        """
        # Simple entity extraction
        def extract_entities(text: str) -> set[str]:
            entities = set()

            # Capitalized words
            caps = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", text)
            entities.update(caps)

            # Numbers
            numbers = re.findall(r"\b\d{3,}\b", text)
            entities.update(numbers)

            # Chinese words (2-4 chars)
            chinese = re.findall(r"[一-鿿]{2,4}", text)
            entities.update(chinese)

            return entities

        query_entities = extract_entities(query)
        content_entities = extract_entities(content)

        if not query_entities:
            return 0.0

        overlap = len(query_entities & content_entities)
        return overlap / len(query_entities)

    def compute_recency_score(
        self,
        chunk_metadata: dict[str, Any],
    ) -> float:
        """
        Compute recency score based on document age.

        Newer documents get higher scores.
        """
        # Would use document created_at timestamp
        # Placeholder: use chunk index (earlier chunks slightly favored)
        chunk_index = chunk_metadata.get("chunk_index", 0)

        # Normalize: earlier chunks get slightly higher score
        if chunk_index < 10:
            return 0.9
        elif chunk_index < 50:
            return 0.7
        else:
            return 0.5

    def compute_authority_score(
        self,
        document_stats: dict[str, Any] | None = None,
    ) -> float:
        """
        Compute source authority score.

        Documents with higher access count are more authoritative.
        """
        if document_stats is None:
            return 0.5

        access_count = document_stats.get("access_count", 0)

        # Normalize
        if access_count > 100:
            return 0.9
        elif access_count > 10:
            return 0.7
        else:
            return 0.5

    def rank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Rank candidates using heuristic features.

        Args:
            query: Original query
            candidates: List of candidates from fusion
            top_k: Number to keep after ranking

        Returns:
            Ranked candidates with coarse_score
        """
        start_time = time.time()

        scored_candidates = []

        for candidate in candidates:
            content = candidate.get("content", "")

            # Compute individual scores
            tfidf = self.compute_tfidf_similarity(query, content)
            entity = self.compute_entity_overlap(query, content)
            recency = self.compute_recency_score(candidate)
            authority = self.compute_authority_score(
                candidate.get("document_stats")
            )

            # Weighted combination
            # TF-IDF most important, then entity overlap
            coarse_score = (
                0.4 * tfidf +
                0.3 * entity +
                0.15 * recency +
                0.15 * authority
            )

            candidate_copy = candidate.copy()
            candidate_copy["coarse_score"] = coarse_score

            scored_candidates.append(candidate_copy)

        # Sort by coarse score
        scored_candidates.sort(
            key=lambda x: x["coarse_score"],
            reverse=True,
        )

        # Keep top_k
        ranked = scored_candidates[:top_k]

        latency = (time.time() - start_time) * 1000

        logger.debug(
            f"Coarse ranking: {len(candidates)} → {len(ranked)} "
            f"in {latency:.2f}ms"
        )

        return ranked


def get_coarse_ranker() -> CoarseRanker:
    """Get coarse ranker instance."""
    return CoarseRanker()