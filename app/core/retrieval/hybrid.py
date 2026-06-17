"""
Hybrid Retrieval Orchestrator

Coordinates three-way parallel retrieval with fusion.
"""

import asyncio
import time
from typing import Any

from app.config import settings
from app.core.retrieval.dense import DenseRetriever
from app.core.retrieval.sparse import SparseRetriever
from app.core.retrieval.graph import GraphRetriever
from app.core.retrieval.fusion import DynamicWeightFusion
from app.models.schemas import QueryType, RetrievalMode, RetrievalCandidate
from app.utils.exceptions import SearchError
from app.utils.logging import get_logger

logger = get_logger("core.retrieval.hybrid")


class HybridRetriever:
    """
    Three-way hybrid retrieval orchestrator.

    Supports:
    - Full hybrid (dense + sparse + graph)
    - Dense only
    - Sparse only
    - Graph only
    """

    def __init__(
        self,
        milvus_collection: str,
        es_index: str,
        neo4j_label: str,
        tenant_id: str,
    ):
        self.milvus_collection = milvus_collection
        self.es_index = es_index
        self.neo4j_label = neo4j_label
        self.tenant_id = tenant_id

        # Initialize retrievers
        self.dense = DenseRetriever(milvus_collection, tenant_id)
        self.sparse = SparseRetriever(es_index, tenant_id)
        self.graph = GraphRetriever(neo4j_label, tenant_id)

        # Fusion
        self.fusion = DynamicWeightFusion()

        # Latency tracking
        self.dense_latency_ms: float | None = None
        self.sparse_latency_ms: float | None = None
        self.graph_latency_ms: float | None = None
        self.fusion_latency_ms: float | None = None
        self.rerank_latency_ms: float | None = None

        # Query analysis result
        self._query_type: QueryType | None = None
        self._weights_used: dict[str, float] = {}

    async def retrieve(
        self,
        query: str,
        top_k: int = 50,
        mode: RetrievalMode = RetrievalMode.HYBRID,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute hybrid retrieval.

        Args:
            query: Search query
            top_k: Number of candidates to retrieve
            mode: Retrieval mode (hybrid/dense/sparse/graph)
            filters: Optional filters

        Returns:
            List of candidates with scores
        """
        start_time = time.time()

        logger.info(
            f"Hybrid retrieval: query='{query[:50]}...', "
            f"mode={mode.value}, top_k={top_k}"
        )

        # Compute dynamic weights for fusion
        self._weights_used = self.fusion.compute_weights(query)
        self._query_type = self._classify_query(query)

        # Extract filter params
        document_ids = filters.get("document_ids") if filters else None

        # Parallel retrieval based on mode
        try:
            if mode == RetrievalMode.HYBRID:
                # Parallel three-way retrieval
                dense_task = self.dense.retrieve(
                    query, top_k, document_ids, filters
                )
                sparse_task = self.sparse.retrieve(
                    query, top_k, document_ids, filters
                )
                graph_task = self.graph.retrieve(query, top_k)

                dense_results, sparse_results, graph_results = await asyncio.gather(
                    dense_task, sparse_task, graph_task,
                    return_exceptions=True,
                )

                # Handle exceptions
                if isinstance(dense_results, Exception):
                    logger.warning(f"Dense retrieval failed: {dense_results}")
                    dense_results = []
                if isinstance(sparse_results, Exception):
                    logger.warning(f"Sparse retrieval failed: {sparse_results}")
                    sparse_results = []
                if isinstance(graph_results, Exception):
                    logger.warning(f"Graph retrieval failed: {graph_results}")
                    graph_results = []

                # Track latencies
                self.dense_latency_ms = self.dense.get_latency()
                self.sparse_latency_ms = self.sparse.get_latency()
                self.graph_latency_ms = self.graph.get_latency()

                # Fuse results
                fused = self.fusion.fuse(
                    dense_results,
                    sparse_results,
                    graph_results,
                    self._weights_used,
                )
                self.fusion_latency_ms = self.fusion.get_latency()

                candidates = fused

            elif mode == RetrievalMode.DENSE:
                candidates = await self.dense.retrieve(
                    query, top_k, document_ids, filters
                )
                self.dense_latency_ms = self.dense.get_latency()

            elif mode == RetrievalMode.SPARSE:
                candidates = await self.sparse.retrieve(
                    query, top_k, document_ids, filters
                )
                self.sparse_latency_ms = self.sparse.get_latency()

            elif mode == RetrievalMode.GRAPH:
                candidates = await self.graph.retrieve(query, top_k)
                self.graph_latency_ms = self.graph.get_latency()

            else:
                raise SearchError(query, "hybrid", f"Unknown mode: {mode}")

            total_latency = (time.time() - start_time) * 1000

            logger.info(
                f"Retrieval complete: {len(candidates)} candidates "
                f"in {total_latency:.2f}ms"
            )

            return candidates

        except Exception as e:
            logger.error(f"Hybrid retrieval failed: {e}")
            raise SearchError(query, "hybrid", str(e))

    def _classify_query(self, query: str) -> QueryType:
        """Simple query classification."""
        query_tokens = len(query.split())

        if query_tokens <= 5:
            return QueryType.ENTITY
        elif query_tokens > 15:
            return QueryType.SEMANTIC
        else:
            return QueryType.MIXED

    def get_query_type(self, query: str) -> QueryType:
        """Get query type for the last query."""
        if self._query_type is None:
            return self._classify_query(query)
        return self._query_type

    def get_weights_used(self) -> dict[str, float]:
        """Get weights used for last retrieval."""
        return self._weights_used

    def get_latencies(self) -> dict[str, float | None]:
        """Get all latency measurements."""
        return {
            "dense_ms": self.dense_latency_ms,
            "sparse_ms": self.sparse_latency_ms,
            "graph_ms": self.graph_latency_ms,
            "fusion_ms": self.fusion_latency_ms,
            "rerank_ms": self.rerank_latency_ms,
        }