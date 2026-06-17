"""
Dense Retrieval - Milvus Vector Search

ANN similarity search using vector embeddings.
"""

import time
import uuid
from typing import Any

from app.config import settings
from app.db.milvus import MilvusClient, get_milvus_client
from app.utils.embeddings import get_embedding_service
from app.utils.exceptions import SearchError
from app.utils.logging import get_logger

logger = get_logger("core.retrieval.dense")


class DenseRetriever:
    """Dense vector retrieval using Milvus."""

    def __init__(
        self,
        collection_name: str,
        tenant_id: str,
    ):
        self.collection_name = collection_name
        self.tenant_id = tenant_id
        self.milvus = get_milvus_client()
        self.embedding_service = get_embedding_service()
        self._latency_ms: float | None = None

    async def retrieve(
        self,
        query: str,
        top_k: int = 50,
        document_ids: list[str] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve similar chunks via vector search.

        Args:
            query: Query text
            top_k: Number of results
            document_ids: Optional filter by document IDs
            filters: Additional filters

        Returns:
            List of candidates with dense_score
        """
        start_time = time.time()

        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.encode_single_async(
                query,
                self.tenant_id,
                use_cache=True,
            )

            # Search in Milvus
            results = await self.milvus.search_vectors_async(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                top_k=top_k,
                tenant_id=self.tenant_id,
                document_ids=document_ids,
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
                    "dense_score": result["score"],  # Cosine similarity
                    "sparse_score": None,
                    "graph_score": None,
                })

            self._latency_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"Dense retrieval: {len(candidates)} results "
                f"in {self._latency_ms:.2f}ms"
            )

            return candidates

        except Exception as e:
            logger.error(f"Dense retrieval failed: {e}")
            raise SearchError(query, "dense", str(e))

    def get_latency(self) -> float | None:
        """Get retrieval latency in ms."""
        return self._latency_ms