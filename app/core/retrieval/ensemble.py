"""
Ensemble Retrieval Orchestrator

Combines the three tenant-aware retrievers (Milvus / ES / Neo4j) into a
single async callable. Fusion is delegated to the project's existing
`DynamicWeightFusion` (weighted RRF) — the same algorithm that has been
producing production-quality hybrid search results.

We don't use `langchain.retrievers.EnsembleRetriever` because:
1. It was removed from `langchain` >= 0.3 and not re-exported from
   `langchain_community` in the version we depend on.
2. `DynamicWeightFusion` already implements query-aware dynamic weighting
   (entity/semantic/mixed), which `EnsembleRetriever` does not support.
"""

from __future__ import annotations

from langchain_core.documents import Document
from pydantic import Field

from app.core.embeddings.bge_m3 import get_bge_m3
from app.core.retrieval.fusion import DynamicWeightFusion
from app.core.retrieval.langchain_retrievers import (
    ESTenantRetriever,
    MilvusTenantRetriever,
    Neo4jTenantRetriever,
)
from app.db.elasticsearch import get_es_client
from app.db.milvus import get_milvus_client
from app.db.neo4j import get_neo4j_client
from app.utils.logging import get_logger

logger = get_logger("core.retrieval.ensemble")


class HybridEnsembleRetriever:
    """
    Async ensemble retriever that runs Milvus + ES + Neo4j in parallel
    and fuses results with the project's `DynamicWeightFusion`.

    Implements the LangChain `BaseRetriever` interface so it can be
    dropped into any LCEL chain.
    """

    # Mark as pydantic-compatible for future BaseRetriever inheritance.
    model_config = {"arbitrary_types_allowed": True}

    top_k: int = 50
    fusion: DynamicWeightFusion = Field(default_factory=DynamicWeightFusion)

    def __init__(
        self,
        tenant: object,
        weights: dict[str, float] | None = None,
        top_k: int = 50,
        **_kwargs,
    ) -> None:
        self.tenant = tenant
        self.top_k = top_k
        self.fusion = DynamicWeightFusion()
        self._weights = weights

        milvus = get_milvus_client()
        es = get_es_client()
        neo4j = get_neo4j_client()

        self.dense = MilvusTenantRetriever(
            collection_name=tenant.get_milvus_collection(),
            tenant_id=str(tenant.id),
            embedding=get_bge_m3(),
            milvus=milvus,
            top_k=top_k,
        )
        self.sparse = ESTenantRetriever(
            index_name=tenant.get_es_index(),
            tenant_id=str(tenant.id),
            es=es,
            top_k=top_k,
        )
        self.graph = Neo4jTenantRetriever(
            label=tenant.get_neo4j_label(),
            tenant_id=str(tenant.id),
            neo4j=neo4j,
            top_k=top_k,
        )
        logger.debug(
            f"HybridEnsembleRetriever built for tenant {tenant.id} (top_k={top_k})"
        )

    async def _afetch_each(
        self, query: str
    ) -> tuple[list[Document], list[Document], list[Document]]:
        import asyncio

        return await asyncio.gather(
            self.dense._aget_relevant_documents(query),
            self.sparse._aget_relevant_documents(query),
            self.graph._aget_relevant_documents(query),
            return_exceptions=False,
        )

    async def ainvoke(self, query: str) -> list[Document]:
        """Async retrieval + fusion. Returns the fused document list."""
        dense_docs, sparse_docs, graph_docs = await self._afetch_each(query)

        weights = self._weights or self.fusion.compute_weights(query)

        # Convert each channel's docs to the project's dict shape, fuse,
        # then re-wrap as LangChain Documents (sorted by fusion score).
        from app.core.retrieval.hybrid import _docs_to_candidates

        candidates = self.fusion.fuse(
            dense_results=_docs_to_candidates(dense_docs, channel="dense"),
            sparse_results=_docs_to_candidates(sparse_docs, channel="sparse"),
            graph_results=_docs_to_candidates(graph_docs, channel="graph"),
            weights=weights,
        )
        # Re-wrap top-k as Documents
        fused_docs: list[Document] = []
        for c in candidates[: self.top_k]:
            fused_docs.append(
                Document(
                    page_content=c.get("content", ""),
                    metadata={
                        "chunk_id": str(c.get("chunk_id") or ""),
                        "document_id": str(c.get("document_id") or ""),
                        "chunk_index": c.get("chunk_index"),
                        "page_number": c.get("page_number"),
                        "chunk_type": c.get("chunk_type", "text"),
                        "heading_text": c.get("heading_text"),
                        "channel": "fused",
                        "dense_score": c.get("dense_score"),
                        "sparse_score": c.get("sparse_score"),
                        "graph_score": c.get("graph_score"),
                        "fusion_score": c.get("fusion_score"),
                    },
                )
            )
        return fused_docs

    def invoke(self, query: str) -> list[Document]:
        """Sync entry point — bridges to async."""
        import asyncio

        return asyncio.run(self.ainvoke(query))


def build_ensemble_retriever(
    tenant: object,
    weights: dict[str, float] | None = None,
    top_k: int = 50,
) -> HybridEnsembleRetriever:
    """Convenience constructor."""
    return HybridEnsembleRetriever(tenant=tenant, weights=weights, top_k=top_k)


__all__ = ["HybridEnsembleRetriever", "build_ensemble_retriever"]