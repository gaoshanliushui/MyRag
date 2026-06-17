"""
Dynamic Weight Fusion Algorithm

Core innovation: Query type detection + dynamic weight fusion.

Query Types:
- Entity: Short entity lookup (names, IDs) → Higher sparse weight
- Semantic: Long semantic query (questions, descriptions) → Higher dense weight
- Mixed: Combination of both → Balanced weights

Fusion: Reciprocal Rank Fusion (RRF) with dynamic weights
"""

import re
import time
from typing import Any

from app.config import settings
from app.models.schemas import QueryType
from app.utils.logging import get_logger

logger = get_logger("core.retrieval.fusion")


class QueryAnalyzer:
    """Analyze query to determine type and features."""

    def analyze(self, query: str) -> tuple[QueryType, dict[str, float]]:
        """
        Analyze query and return type with features.

        Features:
        - length: Query length in tokens
        - entity_count: Number of potential entities
        - question_type: Type of question (who/what/how/why)
        - keyword_density: Ratio of keywords

        Returns:
            (QueryType, features dict)
        """
        features = {}

        # Length estimation
        query_tokens = len(query.split())
        features["length"] = query_tokens

        # Entity detection
        entities = self._detect_entities(query)
        features["entity_count"] = len(entities)

        # Question type
        question_type = self._detect_question_type(query)
        features["question_type"] = question_type

        # Keyword density
        keyword_ratio = self._compute_keyword_ratio(query)
        features["keyword_ratio"] = keyword_ratio

        # Determine query type
        query_type = self._classify_query_type(features)

        logger.debug(
            f"Query analysis: type={query_type.value}, "
            f"features={features}"
        )

        return query_type, features

    def _detect_entities(self, query: str) -> list[str]:
        """Detect potential entities in query."""
        entities = []

        # Capitalized words
        caps = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", query)
        entities.extend(caps)

        # Quoted strings
        quoted = re.findall(r'"([^"]+)"', query)
        entities.extend(quoted)

        # Numbers/IDs
        numbers = re.findall(r"\b\d{3,}\b", query)
        entities.extend(numbers)

        # Chinese proper nouns (2-4 chars, not common words)
        chinese = re.findall(r"[一-鿿]{2,4}", query)
        common = {"什么", "如何", "怎样", "为什么", "哪里", "哪个", "多少"}
        entities.extend([w for w in chinese if w not in common])

        return entities[:10]

    def _detect_question_type(self, query: str) -> str:
        """Detect question type."""
        query_lower = query.lower()

        patterns = {
            "who": ["谁", "who", "which person", "哪个"],
            "what": ["什么", "what", "定义", "definition"],
            "how": ["如何", "怎样", "怎么", "how", "方法"],
            "why": ["为什么", "why", "原因", "reason"],
            "where": ["哪里", "where", "位置", "location"],
            "when": ["何时", "when", "时间", "time"],
        }

        for qtype, keywords in patterns.items():
            for kw in keywords:
                if kw in query_lower:
                    return qtype

        return "general"

    def _compute_keyword_ratio(self, query: str) -> float:
        """Compute ratio of keywords (non-stopwords)."""
        # Simple stopwords list
        stopwords = {"的", "是", "在", "和", "有", "被", "这", "那", "了", "着", "the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "and", "but", "if", "or", "because", "until", "while", "although", "though"}

        words = query.lower().split()
        if not words:
            return 0.0

        non_stop = [w for w in words if w not in stopwords]
        return len(non_stop) / len(words)

    def _classify_query_type(self, features: dict[str, float]) -> QueryType:
        """Classify query type based on features."""
        length = features["length"]
        entity_count = features["entity_count"]

        # Entity query: Short, contains entities
        if length <= 5 and entity_count >= 1:
            return QueryType.ENTITY

        # Semantic query: Long, no entities, question words
        if length > 10 and entity_count == 0:
            return QueryType.SEMANTIC

        # Mixed: Has both characteristics
        return QueryType.MIXED


class DynamicWeightFusion:
    """
    Dynamic weight fusion for hybrid retrieval.

    Uses RRF with weights determined by query type.
    """

    def __init__(
        self,
        k: int = None,
        alpha: float = None,
        beta: float = None,
    ):
        self.k = k or settings.FUSION_K
        self.alpha = alpha or settings.FUSION_ALPHA
        self.beta = beta or settings.FUSION_BETA
        self.analyzer = QueryAnalyzer()
        self._weights: dict[str, float] = {}
        self._latency_ms: float | None = None

    def compute_weights(
        self,
        query: str,
    ) -> dict[str, float]:
        """
        Compute dynamic weights based on query.

        Returns weights for dense, sparse, graph.
        """
        query_type, features = self.analyzer.analyze(query)

        # Base weights per query type
        base_weights = {
            QueryType.ENTITY: {"dense": 0.3, "sparse": 0.5, "graph": 0.2},
            QueryType.SEMANTIC: {"dense": 0.6, "sparse": 0.2, "graph": 0.2},
            QueryType.MIXED: {"dense": 0.4, "sparse": 0.3, "graph": 0.3},
        }

        weights = base_weights[query_type].copy()

        # Adjust based on features
        # Longer queries -> more dense weight
        if features["length"] > 15:
            weights["dense"] += self.alpha
            weights["sparse"] -= self.alpha

        # More entities -> more sparse/graph weight
        if features["entity_count"] > 2:
            weights["sparse"] += self.beta
            weights["graph"] += self.beta
            weights["dense"] -= self.beta

        # Normalize weights
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

        self._weights = weights

        logger.info(
            f"Computed weights for {query_type.value} query: "
            f"dense={weights['dense']:.2f}, "
            f"sparse={weights['sparse']:.2f}, "
            f"graph={weights['graph']:.2f}"
        )

        return weights

    def fuse(
        self,
        dense_results: list[dict[str, Any]],
        sparse_results: list[dict[str, Any]],
        graph_results: list[dict[str, Any]],
        weights: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fuse results using weighted RRF.

        RRF formula: score = Σ (weight_i / (k + rank_i))

        Args:
            dense_results: Results from dense retrieval
            sparse_results: Results from sparse retrieval
            graph_results: Results from graph retrieval
            weights: Optional custom weights

        Returns:
            Fused and ranked candidates
        """
        start_time = time.time()

        weights = weights or self._weights or {"dense": 0.4, "sparse": 0.3, "graph": 0.3}

        # Build rank maps for each retriever
        def build_rank_map(results: list[dict], score_key: str) -> dict[str, tuple[int, float]]:
            rank_map = {}
            for rank, result in enumerate(results):
                chunk_id = str(result.get("chunk_id", ""))
                score = result.get(score_key, 0)
                rank_map[chunk_id] = (rank + 1, score)
            return rank_map

        dense_ranks = build_rank_map(dense_results, "dense_score")
        sparse_ranks = build_rank_map(sparse_results, "sparse_score")
        graph_ranks = build_rank_map(graph_results, "graph_score")

        # Collect all unique chunk IDs
        all_ids = set()
        all_ids.update(dense_ranks.keys())
        all_ids.update(sparse_ranks.keys())
        all_ids.update(graph_ranks.keys())

        # Compute RRF scores
        fused_results: dict[str, dict[str, Any]] = {}

        for chunk_id in all_ids:
            score = 0.0

            # Dense contribution
            if chunk_id in dense_ranks:
                rank, original_score = dense_ranks[chunk_id]
                score += weights["dense"] / (self.k + rank)

            # Sparse contribution
            if chunk_id in sparse_ranks:
                rank, original_score = sparse_ranks[chunk_id]
                score += weights["sparse"] / (self.k + rank)

            # Graph contribution
            if chunk_id in graph_ranks:
                rank, original_score = graph_ranks[chunk_id]
                score += weights["graph"] / (self.k + rank)

            # Get best content representation
            result_data = None
            if chunk_id in dense_ranks:
                idx = dense_ranks[chunk_id][0] - 1
                if idx < len(dense_results):
                    result_data = dense_results[idx]
            elif chunk_id in sparse_ranks:
                idx = sparse_ranks[chunk_id][0] - 1
                if idx < len(sparse_results):
                    result_data = sparse_results[idx]
            elif chunk_id in graph_ranks:
                idx = graph_ranks[chunk_id][0] - 1
                if idx < len(graph_results):
                    result_data = graph_results[idx]

            if result_data:
                # Update with fusion score
                result_copy = result_data.copy()

                # Preserve original scores
                if chunk_id in dense_ranks:
                    result_copy["dense_score"] = dense_ranks[chunk_id][1]
                if chunk_id in sparse_ranks:
                    result_copy["sparse_score"] = sparse_ranks[chunk_id][1]
                if chunk_id in graph_ranks:
                    result_copy["graph_score"] = graph_ranks[chunk_id][1]

                result_copy["fusion_score"] = score
                fused_results[chunk_id] = result_copy

        # Sort by fusion score
        sorted_results = sorted(
            fused_results.values(),
            key=lambda x: x["fusion_score"],
            reverse=True,
        )

        self._latency_ms = (time.time() - start_time) * 1000

        logger.debug(
            f"Fusion complete: {len(sorted_results)} candidates "
            f"in {self._latency_ms:.2f}ms"
        )

        return sorted_results

    def get_weights(self) -> dict[str, float]:
        """Get current weights."""
        return self._weights

    def get_latency(self) -> float | None:
        """Get fusion latency."""
        return self._latency_ms