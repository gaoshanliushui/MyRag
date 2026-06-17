"""
Sparse Retrieval - Elasticsearch BM25

Keyword-based retrieval with field weighting.
"""

import time
import uuid
from typing import Any

from app.db.elasticsearch import ESClient, get_es_client
from app.utils.exceptions import SearchError
from app.utils.logging import get_logger

logger = get_logger("core.retrieval.sparse")


class SparseRetriever:
    """BM25 sparse retrieval using Elasticsearch."""

    def __init__(
        self,
        index_name: str,
        tenant_id: str,
    ):
        self.index_name = index_name
        self.tenant_id = tenant_id
        self._es_client: ESClient | None = None
        self._latency_ms: float | None = None

    async def get_client(self) -> ESClient:
        """Get Elasticsearch client."""
        if self._es_client is None:
            self._es_client = await get_es_client()
        return self._es_client

    async def retrieve(
        self,
        query: str,
        top_k: int = 50,
        document_ids: list[str] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve chunks via BM25 search.

        Args:
            query: Query text
            top_k: Number of results
            document_ids: Optional filter by document IDs
            filters: Additional filters

        Returns:
            List of candidates with sparse_score
        """
        start_time = time.time()

        try:
            es = await self.get_client()

            # BM25 search
            results = await es.bm25_search(
                index_name=self.index_name,
                query=query,
                top_k=top_k,
                tenant_id=self.tenant_id,
                document_ids=document_ids,
                filters=filters,
            )

            # Process results
            candidates = []
            for result in results:
                candidates.append({
                    "chunk_id": uuid.UUID(result["id"]) if result["id"] else None,
                    "document_id": uuid.UUID(result["document_id"]) if result["document_id"] else None,
                    "chunk_index": result["chunk_index"],
                    "page_number": result["page_number"],
                    "chunk_type": result["chunk_type"],
                    "heading_text": result["heading_text"],
                    "content": result["content"],
                    "dense_score": None,
                    "sparse_score": result["score"],  # BM25 score
                    "graph_score": None,
                })

            self._latency_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"Sparse retrieval: {len(candidates)} results "
                f"in {self._latency_ms:.2f}ms"
            )

            return candidates

        except Exception as e:
            logger.error(f"Sparse retrieval failed: {e}")
            raise SearchError(query, "sparse", str(e))

    def get_latency(self) -> float | None:
        """Get retrieval latency in ms."""
        return self._latency_ms