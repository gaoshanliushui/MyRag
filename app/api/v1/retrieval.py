"""
Retrieval and QA Endpoints

Hybrid search and question answering with RAG.
"""

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentTenant, DBSession
from app.config import settings
from app.core.monitoring.metrics import record_query_metrics, record_retrieval_metrics
from app.core.retrieval.hybrid import HybridRetriever
from app.core.ranking.confidence import ConfidenceScorer
from app.core.ranking.conflict import ConflictDetector
from app.models.document import Document
from app.models.schemas import (
    ConflictInfo,
    QARequest,
    QAResponse,
    QASource,
    QueryType,
    RetrievalCandidate,
    RetrievalMetrics,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResponse,
    RetrievedChunk,
    ChunkSource,
)
from app.models.tenant import Tenant
from app.utils.logging import get_logger

logger = get_logger("api.retrieval")

router = APIRouter()


@router.post("/search", response_model=RetrievalResponse)
async def search(
    tenant: CurrentTenant,
    session: DBSession,
    request: RetrievalRequest,
) -> RetrievalResponse:
    """
    Hybrid search across documents.

    Supports three retrieval modes:
    - hybrid: Dense + Sparse + Graph with dynamic fusion
    - dense: Vector similarity only
    - sparse: BM25 keyword search only
    - graph: Knowledge graph multi-hop
    """
    start_time = time.time()

    logger.info(
        f"Search request from tenant {tenant.name}: "
        f"query='{request.query[:50]}...', mode={request.mode}"
    )

    # Get tenant resources
    collection_name = tenant.get_milvus_collection()
    es_index = tenant.get_es_index()
    neo4j_label = tenant.get_neo4j_label()

    # Initialize retriever
    retriever = HybridRetriever(
        milvus_collection=collection_name,
        es_index=es_index,
        neo4j_label=neo4j_label,
        tenant_id=str(tenant.id),
    )

    # Execute retrieval
    candidates = await retriever.retrieve(
        query=request.query,
        top_k=request.top_k,
        mode=request.mode,
        filters=request.filters,
    )

    retrieval_latency = (time.time() - start_time) * 1000

    # Apply reranking if enabled
    if request.enable_reranking and len(candidates) > 0:
        from app.core.ranking.fine import FineRanker
        ranker = FineRanker()
        candidates = await ranker.rerank(
            query=request.query,
            candidates=candidates,
            top_k=request.top_k,
        )

    # Apply confidence scoring if enabled
    if request.enable_confidence:
        scorer = ConfidenceScorer()
        for candidate in candidates:
            candidate.confidence = await scorer.score_confidence(candidate)

    # Apply conflict detection if enabled
    conflicts = []
    if request.enable_conflict_detection and len(candidates) >= 2:
        detector = ConflictDetector()
        conflicts = await detector.detect_conflicts(candidates)

    # Build response
    # Get document names for sources
    document_ids = [c.chunk.document_id for c in candidates]
    doc_result = await session.execute(
        select(Document.id, Document.original_filename).where(
            Document.id.in_(document_ids)
        )
    )
    doc_names = {row[0]: row[1] for row in doc_result.all()}

    results = []
    for i, candidate in enumerate(candidates):
        candidate.final_rank = i + 1
        source = ChunkSource(
            chunk_id=candidate.chunk_id,
            document_id=candidate.document_id,
            document_name=doc_names.get(candidate.document_id, "Unknown"),
            page_number=candidate.page_number,
            chunk_index=candidate.chunk_index,
            heading_text=candidate.heading_text,
            excerpt=candidate.content[:300],
            score=candidate.fusion_score or candidate.rerank_score or 0.0,
        )
        results.append(RetrievedChunk(chunk=candidate, source=source))

    # Determine query type from retriever
    query_type = retriever.get_query_type(request.query)

    # Build metrics
    metrics = RetrievalMetrics(
        latency_ms=retrieval_latency,
        dense_latency_ms=retriever.dense_latency_ms,
        sparse_latency_ms=retriever.sparse_latency_ms,
        graph_latency_ms=retriever.graph_latency_ms,
        fusion_latency_ms=retriever.fusion_latency_ms,
        rerank_latency_ms=retriever.rerank_latency_ms,
        total_candidates=len(candidates),
        final_candidates=len(results),
        query_type=query_type,
        weights_used=retriever.get_weights_used(),
    )

    # Record metrics
    record_query_metrics(str(tenant.id), query_type.value, request.mode.value, retrieval_latency)
    record_retrieval_metrics(
        str(tenant.id),
        retriever.dense_latency_ms,
        retriever.sparse_latency_ms,
        retriever.graph_latency_ms,
    )

    # Update tenant query count
    tenant.queries_today += 1
    from datetime import datetime
    tenant.last_query_date = datetime.utcnow()
    await session.flush()

    logger.info(
        f"Search completed: {len(results)} results in {retrieval_latency:.2f}ms"
    )

    return RetrievalResponse(
        query=request.query,
        results=results,
        conflicts=conflicts,
        metrics=metrics,
        has_more=False,
        page=1,
    )


@router.post("/qa", response_model=QAResponse)
async def question_answer(
    tenant: CurrentTenant,
    session: DBSession,
    request: QARequest,
) -> QAResponse:
    """
    Question answering with RAG.

    1. Retrieve relevant chunks using hybrid search
    2. Rerank and filter for quality
    3. Generate answer using LLM
    4. Include source citations with page numbers
    """
    start_time = time.time()

    logger.info(
        f"QA request from tenant {tenant.name}: "
        f"question='{request.question[:50]}...'"
    )

    # First, perform retrieval
    search_request = RetrievalRequest(
        query=request.question,
        top_k=request.top_k,
        mode=request.mode,
        enable_reranking=request.enable_reranking,
        enable_confidence=request.enable_confidence,
        enable_conflict_detection=request.enable_conflict_detection,
        filters=request.filters,
    )

    # Get search results (reuse search logic)
    search_response = await search(tenant, session, search_request)

    # Filter by confidence if enabled
    if request.enable_confidence:
        threshold = settings.CONFIDENCE_THRESHOLD
        search_response.results = [
            r for r in search_response.results
            if r.chunk.confidence and r.chunk.confidence >= threshold
        ]

    # Build sources list for the response payload (citations)
    sources = []
    for result in search_response.results[:5]:  # Top 5 for context
        sources.append(QASource(
            document_id=result.source.document_id,
            document_name=result.source.document_name,
            page_number=result.source.page_number,
            chunk_id=result.source.chunk_id,
            excerpt=result.source.excerpt,
            relevance_score=result.source.score,
        ))

    # Generate answer using the LangChain LCEL QA chain.
    # The chain encapsulates: ensemble retrieval → context formatting →
    # prompt template → chat model → string output.
    from app.core.chains.qa_chain import build_qa_chain
    from app.core.retrieval.fusion import DynamicWeightFusion

    fusion_engine = DynamicWeightFusion()
    weights = fusion_engine.compute_weights(request.question)
    chain = build_qa_chain(tenant, weights=weights, top_k=request.top_k)

    answer = await chain.ainvoke(request.question)
    model_used = settings.LLM_MODEL

    # Calculate overall confidence
    confidence = 0.0
    if sources:
        confidence = sum(s.relevance_score for s in sources) / len(sources)

    # Build response
    from datetime import datetime

    return QAResponse(
        question=request.question,
        answer=answer,
        sources=sources,
        confidence=confidence,
        conflicts=search_response.conflicts,
        metrics=search_response.metrics,
        generated_at=datetime.utcnow(),
        model_used=model_used,
    )


@router.get("/sources/{chunk_id}")
async def get_chunk_source(
    chunk_id: uuid.UUID,
    tenant: CurrentTenant,
    session: DBSession,
) -> dict[str, Any]:
    """Get detailed source information for a chunk."""
    from app.models.document import Chunk

    result = await session.execute(
        select(Chunk).where(
            Chunk.id == chunk_id,
            Chunk.tenant_id == tenant.id,
        )
    )
    chunk = result.scalar_one_or_none()

    if not chunk:
        return {"error": "Chunk not found"}

    # Get document info
    doc_result = await session.execute(
        select(Document).where(Document.id == chunk.document_id)
    )
    document = doc_result.scalar_one_or_none()

    return {
        "chunk_id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "document_name": document.original_filename if document else "Unknown",
        "page_number": chunk.page_number,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "heading_text": chunk.heading_text,
        "chunk_type": chunk.chunk_type.value,
    }