"""
LangChain-compatible Retrievers for MyRag

Each retriever is a `BaseRetriever` subclass that wraps one of the project's
existing DB clients (MilvusClient / ESClient / Neo4jClient). They translate
the project's multi-tenant naming into LangChain's standard `Document` interface.

The native DB clients are kept as-is to preserve the 9-field schema, BM25
field-weighting, multi-hop Cypher queries, and the per-tenant resource names
that `Tenant.get_milvus_collection()` / `get_es_index()` / `get_neo4j_label()`
already manage.
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from app.utils.logging import get_logger

logger = get_logger("core.retrieval.langchain_retrievers")


def _hit_to_document(hit: dict[str, Any], channel: str) -> Document:
    """Convert a project-specific hit dict to a LangChain `Document`."""
    return Document(
        page_content=hit.get("content", ""),
        metadata={
            "chunk_id": str(hit.get("chunk_id", "")),
            "document_id": str(hit.get("document_id", "")),
            "chunk_index": hit.get("chunk_index"),
            "page_number": hit.get("page_number"),
            "chunk_type": hit.get("chunk_type", "text"),
            "heading_text": hit.get("heading_text"),
            "channel": channel,
            f"{channel}_score": hit.get(f"{channel}_score") or hit.get("score"),
        },
    )


class MilvusTenantRetriever(BaseRetriever):
    """LangChain retriever backed by the project's `MilvusClient`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    collection_name: str
    tenant_id: str
    embedding: Embeddings
    milvus: Any = Field(exclude=True)
    top_k: int = 50
    document_ids: list[str] | None = None

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        return asyncio.run(self._aget_relevant_documents(query, run_manager=run_manager))

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        vec = self.embedding.embed_query(query)
        try:
            hits = await self.milvus.search_vectors_async(
                collection_name=self.collection_name,
                query_vector=vec,
                top_k=self.top_k,
                tenant_id=self.tenant_id,
                document_ids=self.document_ids,
            )
        except Exception as exc:
            logger.error(f"Milvus retrieval failed: {exc}")
            return []
        return [_hit_to_document(h, "dense") for h in hits]


class ESTenantRetriever(BaseRetriever):
    """LangChain retriever backed by the project's `ESClient` (BM25)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    index_name: str
    tenant_id: str
    es: Any = Field(exclude=True)
    top_k: int = 50
    document_ids: list[str] | None = None
    filters: dict[str, Any] | None = None

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        return asyncio.run(self._aget_relevant_documents(query, run_manager=run_manager))

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        try:
            hits = await self.es.bm25_search(
                index_name=self.index_name,
                query=query,
                top_k=self.top_k,
                tenant_id=self.tenant_id,
                document_ids=self.document_ids,
                filters=self.filters,
            )
        except Exception as exc:
            logger.error(f"ES BM25 retrieval failed: {exc}")
            return []
        return [_hit_to_document(h, "sparse") for h in hits]


class Neo4jTenantRetriever(BaseRetriever):
    """LangChain retriever backed by the project's `Neo4jClient` (multi-hop)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    label: str
    tenant_id: str
    neo4j: Any = Field(exclude=True)
    top_k: int = 50
    max_hops: int = 2

    def _extract_entities(self, query: str) -> list[str]:
        """Same heuristic entity extraction as the legacy `GraphRetriever`."""
        import re

        entities: list[str] = []
        entities.extend(re.findall(r'"([^"]+)"', query))
        entities.extend(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", query))
        common_words = {"公司", "银行", "政府", "部门", "机构", "企业"}
        chinese = re.findall(r"[一-鿿]{2,4}", query)
        entities.extend([w for w in chinese if w not in common_words])
        return entities[:10]

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        return asyncio.run(self._aget_relevant_documents(query, run_manager=run_manager))

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        entities = self._extract_entities(query)
        if not entities:
            return []
        try:
            hits = await self.neo4j.multi_hop_search_async(
                label=self.label,
                query_entities=entities,
                max_hops=self.max_hops,
                top_k=self.top_k,
            )
        except Exception as exc:
            logger.error(f"Neo4j retrieval failed: {exc}")
            return []
        # `content_preview` is what the project returns for graph hits
        normalised = []
        for h in hits:
            h = dict(h)
            if "content" not in h or not h["content"]:
                h["content"] = h.get("content_preview", "")
            normalised.append(h)
        return [_hit_to_document(h, "graph") for h in normalised]