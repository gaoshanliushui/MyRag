"""
Hybrid Retrieval Orchestrator

Three-way parallel retrieval orchestrator that delegates to the LangChain
`EnsembleRetriever` built from `app.core.retrieval.langchain_retrievers`.

Preserves the legacy public surface (`retrieve(...)`, `get_query_type`,
`get_weights_used`, latency tracking) so the API endpoints need no changes.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_core.documents import Document

from app.config import settings
from app.core.retrieval.ensemble import build_ensemble_retriever
from app.core.retrieval.fusion import DynamicWeightFusion
from app.models.schemas import QueryType, RetrievalMode
from app.utils.exceptions import SearchError
from app.utils.logging import get_logger

logger = get_logger("core.retrieval.hybrid")


class HybridRetriever:
    """Three-way hybrid retrieval orchestrator (LangChain-backed)."""

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

        self.fusion = DynamicWeightFusion()

        # Per-channel latency (ms) — populated by retrieve()
        self.dense_latency_ms: float | None = None
        self.sparse_latency_ms: float | None = None
        self.graph_latency_ms: float | None = None
        self.fusion_latency_ms: float | None = None
        self.rerank_latency_ms: float | None = None

        self._query_type: QueryType | None = None
        self._weights_used: dict[str, float] = {}

        # Lightweight tenant shim used by `build_ensemble_retriever`
        self._tenant_shim = _TenantShim(
            id=tenant_id,
            milvus_collection=milvus_collection,
            es_index=es_index,
            neo4j_label=neo4j_label,
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 50,
        mode: RetrievalMode = RetrievalMode.HYBRID,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        start_time = time.time()

        logger.info(
            f"Hybrid retrieval: query='{query[:50]}...', "
            f"mode={mode.value}, top_k={top_k}"
        )

        self._weights_used = self.fusion.compute_weights(query)
        self._query_type = self._classify_query(query)
        document_ids = filters.get("document_ids") if filters else None

        try:
            if mode == RetrievalMode.HYBRID:
                ensemble = build_ensemble_retriever(
                    self._tenant_shim, self._weights_used, top_k=top_k
                )
                # HybridEnsembleRetriever is natively async
                docs: list[Document] = await ensemble.ainvoke(query)
                self.fusion_latency_ms = (time.time() - start_time) * 1000
                candidates = _docs_to_candidates(docs)
            elif mode == RetrievalMode.DENSE:
                from app.core.retrieval.langchain_retrievers import MilvusTenantRetriever
                from app.core.embeddings.bge_m3 import get_bge_m3
                from app.db.milvus import get_milvus_client

                r = MilvusTenantRetriever(
                    collection_name=self.milvus_collection,
                    tenant_id=self.tenant_id,
                    embedding=get_bge_m3(),
                    milvus=get_milvus_client(),
                    top_k=top_k,
                    document_ids=document_ids,
                )
                t0 = time.time()
                docs = await r._aget_relevant_documents(query)
                self.dense_latency_ms = (time.time() - t0) * 1000
                candidates = _docs_to_candidates(docs, channel="dense")
            elif mode == RetrievalMode.SPARSE:
                from app.core.retrieval.langchain_retrievers import ESTenantRetriever
                from app.db.elasticsearch import get_es_client

                r = ESTenantRetriever(
                    index_name=self.es_index,
                    tenant_id=self.tenant_id,
                    es=get_es_client(),
                    top_k=top_k,
                    document_ids=document_ids,
                    filters=filters,
                )
                t0 = time.time()
                docs = await r._aget_relevant_documents(query)
                self.sparse_latency_ms = (time.time() - t0) * 1000
                candidates = _docs_to_candidates(docs, channel="sparse")
            elif mode == RetrievalMode.GRAPH:
                from app.core.retrieval.langchain_retrievers import Neo4jTenantRetriever
                from app.db.neo4j import get_neo4j_client

                r = Neo4jTenantRetriever(
                    label=self.neo4j_label,
                    tenant_id=self.tenant_id,
                    neo4j=get_neo4j_client(),
                    top_k=top_k,
                )
                t0 = time.time()
                docs = await r._aget_relevant_documents(query)
                self.graph_latency_ms = (time.time() - t0) * 1000
                candidates = _docs_to_candidates(docs, channel="graph")
            else:
                raise SearchError(query, "hybrid", f"Unknown mode: {mode}")

            total_latency = (time.time() - start_time) * 1000
            logger.info(
                f"Retrieval complete: {len(candidates)} candidates "
                f"in {total_latency:.2f}ms"
            )
            return candidates

        except Exception as exc:
            logger.error(f"Hybrid retrieval failed: {exc}")
            raise SearchError(query, "hybrid", str(exc))

    def _classify_query(self, query: str) -> QueryType:
        tokens = len(query.split())
        if tokens <= 5:
            return QueryType.ENTITY
        if tokens > 15:
            return QueryType.SEMANTIC
        return QueryType.MIXED

    def get_query_type(self, query: str) -> QueryType:
        if self._query_type is None:
            return self._classify_query(query)
        return self._query_type

    def get_weights_used(self) -> dict[str, float]:
        return self._weights_used

    def get_latencies(self) -> dict[str, float | None]:
        return {
            "dense_ms": self.dense_latency_ms,
            "sparse_ms": self.sparse_latency_ms,
            "graph_ms": self.graph_latency_ms,
            "fusion_ms": self.fusion_latency_ms,
            "rerank_ms": self.rerank_latency_ms,
        }


class _TenantShim:
    """Minimal tenant object exposing only the methods `build_ensemble_retriever` needs."""

    def __init__(
        self,
        id: str,
        milvus_collection: str,
        es_index: str,
        neo4j_label: str,
    ) -> None:
        self.id = id
        self._milvus_collection = milvus_collection
        self._es_index = es_index
        self._neo4j_label = neo4j_label

    def get_milvus_collection(self) -> str:
        return self._milvus_collection

    def get_es_index(self) -> str:
        return self._es_index

    def get_neo4j_label(self) -> str:
        return self._neo4j_label


def _docs_to_candidates(
    docs: list[Document], channel: str | None = None
) -> list[dict[str, Any]]:
    """Convert LangChain `Document` results back to the project's dict-shaped candidates."""
    candidates: list[dict[str, Any]] = []
    for d in docs:
        meta = d.metadata or {}
        ch = channel or meta.get("channel")
        candidates.append(
            {
                "chunk_id": meta.get("chunk_id"),
                "document_id": meta.get("document_id"),
                "chunk_index": meta.get("chunk_index"),
                "page_number": meta.get("page_number"),
                "chunk_type": meta.get("chunk_type", "text"),
                "heading_text": meta.get("heading_text"),
                "content": d.page_content,
                "dense_score": meta.get("dense_score") if ch in ("dense", None) else None,
                "sparse_score": meta.get("sparse_score") if ch in ("sparse", None) else None,
                "graph_score": meta.get("graph_score") if ch in ("graph", None) else None,
                "fusion_score": meta.get(f"{ch}_score") if ch else None,
            }
        )
    return candidates


__all__ = ["HybridRetriever"]