"""
Graph Retrieval - Neo4j Multi-Hop

Knowledge graph-based retrieval via entity traversal.
"""

import re
import time
import uuid
from typing import Any

from app.config import settings
from app.db.neo4j import Neo4jClient, get_neo4j_client
from app.utils.exceptions import SearchError
from app.utils.logging import get_logger

logger = get_logger("core.retrieval.graph")


class GraphRetriever:
    """Knowledge graph retrieval using Neo4j."""

    def __init__(
        self,
        label: str,
        tenant_id: str,
    ):
        self.label = label
        self.tenant_id = tenant_id
        self.neo4j = get_neo4j_client()
        self._latency_ms: float | None = None

    def extract_entities(self, query: str) -> list[str]:
        """
        Extract entities from query.

        Simple approach: extract capitalized words,
        quoted strings, and Chinese proper nouns.
        """
        entities = []

        # Extract quoted strings
        quoted = re.findall(r'"([^"]+)"', query)
        entities.extend(quoted)

        # Extract capitalized words (English names)
        caps = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", query)
        entities.extend(caps)

        # Extract potential Chinese entity patterns
        # This is simplified - real implementation would use NER
        chinese_pattern = re.findall(r"[一-鿿]{2,4}", query)
        # Filter common words
        common_words = {"公司", "银行", "政府", "部门", "机构", "企业"}
        entities.extend([w for w in chinese_pattern if w not in common_words])

        # Limit entities
        return entities[:10]

    async def retrieve(
        self,
        query: str,
        top_k: int = 50,
        max_hops: int = 2,
    ) -> list[dict[str, Any]]:
        """
        Retrieve chunks via multi-hop graph traversal.

        Args:
            query: Query text
            top_k: Number of results
            max_hops: Maximum traversal depth

        Returns:
            List of candidates with graph_score
        """
        start_time = time.time()

        try:
            # Extract entities from query
            entities = self.extract_entities(query)

            if not entities:
                logger.debug("No entities extracted from query")
                self._latency_ms = (time.time() - start_time) * 1000
                return []

            # Multi-hop search
            results = await self.neo4j.multi_hop_search_async(
                label=self.label,
                query_entities=entities,
                max_hops=max_hops,
                top_k=top_k,
            )

            # Process results
            candidates = []
            for result in results:
                # Need to get full content from database
                # Graph search returns preview only
                candidates.append({
                    "chunk_id": uuid.UUID(result["chunk_id"]) if result["chunk_id"] else None,
                    "document_id": uuid.UUID(result["document_id"]) if result["document_id"] else None,
                    "chunk_index": result["chunk_index"],
                    "page_number": result["page_number"],
                    "chunk_type": "text",
                    "heading_text": None,
                    "content": result.get("content_preview", ""),  # May need DB lookup
                    "dense_score": None,
                    "sparse_score": None,
                    "graph_score": result["score"],
                })

            self._latency_ms = (time.time() - start_time) * 1000

            logger.debug(
                f"Graph retrieval: {len(candidates)} results "
                f"via entities {entities} in {self._latency_ms:.2f}ms"
            )

            return candidates

        except Exception as e:
            logger.error(f"Graph retrieval failed: {e}")
            raise SearchError(query, "graph", str(e))

    def get_latency(self) -> float | None:
        """Get retrieval latency in ms."""
        return self._latency_ms