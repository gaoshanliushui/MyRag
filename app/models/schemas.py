"""
Pydantic Schemas - Request/Response Models

All API request and response schemas using Pydantic v2.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Base schema configuration
class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


# Enums (re-exported for schemas)
class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"


class ChunkType(str, Enum):
    TEXT = "text"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FORMULA = "formula"
    LIST = "list"
    CODE = "code"
    METADATA = "metadata"


class RetrievalMode(str, Enum):
    HYBRID = "hybrid"
    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"


class QueryType(str, Enum):
    ENTITY = "entity"  # Short entity lookup
    SEMANTIC = "semantic"  # Long semantic query
    MIXED = "mixed"  # Mixed query


# ============================================
# Tenant Schemas
# ============================================

class TenantCreate(BaseSchema):
    """Request to create a new tenant."""

    name: str = Field(min_length=2, max_length=100)
    slug: str = Field(min_length=2, max_length=50, pattern="^[a-z0-9-]+$")
    admin_email: str | None = Field(None, max_length=255)
    description: str | None = None
    max_documents: int = Field(default=10000, ge=100, le=1000000)
    max_storage_mb: int = Field(default=1000, ge=100, le=100000)
    max_queries_per_day: int = Field(default=10000, ge=100, le=1000000)
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("admin_email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v and "@" not in v:
            raise ValueError("Invalid email format")
        return v


class TenantUpdate(BaseSchema):
    """Request to update a tenant."""

    name: str | None = Field(None, min_length=2, max_length=100)
    admin_email: str | None = Field(None, max_length=255)
    description: str | None = None
    max_documents: int | None = Field(None, ge=100, le=1000000)
    max_storage_mb: int | None = Field(None, ge=100, le=100000)
    max_queries_per_day: int | None = Field(None, ge=100, le=1000000)
    config: dict[str, Any] | None = None
    is_active: bool | None = None


class TenantResponse(BaseSchema):
    """Tenant response."""

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    milvus_collection_name: str
    es_index_name: str
    neo4j_label: str
    config: dict[str, Any]
    max_documents: int
    max_storage_mb: int
    max_queries_per_day: int
    current_documents: int
    current_storage_mb: int
    queries_today: int
    admin_email: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class TenantListResponse(BaseSchema):
    """Paginated tenant list."""

    tenants: list[TenantResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class TenantAPIKeyResponse(BaseSchema):
    """Response with API key (only shown once)."""

    tenant: TenantResponse
    api_key: str


# ============================================
# Document Schemas
# ============================================

class DocumentUpload(BaseSchema):
    """Request metadata for document upload."""

    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseSchema):
    """Document response."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    status: DocumentStatus
    total_pages: int
    total_chunks: int
    total_tokens: int
    access_count: int
    storage_tier: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    processing_error: str | None = None


class DocumentListResponse(BaseSchema):
    """Paginated document list."""

    documents: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class DocumentStatusResponse(BaseSchema):
    """Document processing status."""

    id: uuid.UUID
    status: DocumentStatus
    total_pages: int
    total_chunks: int
    total_tokens: int
    processing_progress: float  # 0.0 to 1.0
    processing_error: str | None = None
    estimated_completion: datetime | None = None


class DocumentDetailResponse(BaseSchema):
    """Document with chunk preview."""

    document: DocumentResponse
    chunks_preview: list["ChunkPreview"]
    chunk_count: int


# ============================================
# Chunk Schemas
# ============================================

class ChunkPreview(BaseSchema):
    """Chunk preview for document detail."""

    id: uuid.UUID
    chunk_index: int
    page_number: int | None
    content_preview: str  # First 200 chars
    chunk_type: ChunkType
    heading_text: str | None


class ChunkResponse(BaseSchema):
    """Full chunk response."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    page_number: int | None
    content: str
    chunk_type: ChunkType
    heading_level: int | None
    heading_text: str | None
    token_count: int
    chunk_metadata: dict[str, Any]
    retrieval_count: int
    created_at: datetime


class ChunkSource(BaseSchema):
    """Source citation for retrieved chunk."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_number: int | None
    chunk_index: int
    heading_text: str | None
    excerpt: str  # Relevant excerpt (first 300 chars)
    score: float


# ============================================
# Retrieval Schemas
# ============================================

class RetrievalRequest(BaseSchema):
    """Request for hybrid retrieval."""

    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    mode: RetrievalMode = RetrievalMode.HYBRID
    enable_reranking: bool = Field(default=True)
    enable_confidence: bool = Field(default=True)
    enable_conflict_detection: bool = Field(default=True)
    filters: dict[str, Any] = Field(default_factory=dict)
    # Filters can include:
    # - document_ids: list of specific documents to search
    # - date_range: {"start": date, "end": date}
    # - metadata_filters: {"field": "value"}
    # - file_types: list of file types


class RetrievalCandidate(BaseSchema):
    """Single retrieval candidate."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    content: str
    page_number: int | None
    chunk_index: int
    chunk_type: ChunkType
    heading_text: str | None
    dense_score: float | None = None
    sparse_score: float | None = None
    graph_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    confidence: float | None = None
    final_rank: int


class RetrievedChunk(BaseSchema):
    """Final retrieved chunk with all scores."""

    chunk: RetrievalCandidate
    source: ChunkSource


class ConflictInfo(BaseSchema):
    """Cross-evidence conflict information."""

    claim: str
    supporting_chunks: list[uuid.UUID]
    contradicting_chunks: list[uuid.UUID]
    confidence: float  # 0.0 = definite conflict, 1.0 = no conflict
    resolution: str | None = None  # LLM-generated resolution if possible


class RetrievalMetrics(BaseSchema):
    """Metrics for retrieval operation."""

    latency_ms: float
    dense_latency_ms: float | None = None
    sparse_latency_ms: float | None = None
    graph_latency_ms: float | None = None
    fusion_latency_ms: float | None = None
    rerank_latency_ms: float | None = None
    total_candidates: int
    final_candidates: int
    query_type: QueryType
    weights_used: dict[str, float]  # {"dense": 0.5, "sparse": 0.3, "graph": 0.2}


class RetrievalResponse(BaseSchema):
    """Response from hybrid retrieval."""

    query: str
    results: list[RetrievedChunk]
    conflicts: list[ConflictInfo] = Field(default_factory=list)
    metrics: RetrievalMetrics
    has_more: bool
    page: int = 1


# ============================================
# QA (Question Answering) Schemas
# ============================================

class QARequest(BaseSchema):
    """Request for question answering."""

    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: RetrievalMode = RetrievalMode.HYBRID
    enable_reranking: bool = Field(default=True)
    enable_confidence: bool = Field(default=True)
    enable_conflict_detection: bool = Field(default=True)
    filters: dict[str, Any] = Field(default_factory=dict)
    stream: bool = Field(default=False)  # Enable streaming response


class QASource(BaseSchema):
    """Source citation in QA answer."""

    document_id: uuid.UUID
    document_name: str
    page_number: int | None
    chunk_id: uuid.UUID
    excerpt: str
    relevance_score: float


class QAResponse(BaseSchema):
    """Response from question answering."""

    question: str
    answer: str
    sources: list[QASource]
    confidence: float
    conflicts: list[ConflictInfo] = Field(default_factory=list)
    metrics: RetrievalMetrics
    generated_at: datetime
    model_used: str | None = None


class QAStreamChunk(BaseSchema):
    """Single chunk in streaming QA response."""

    type: Literal["answer", "source", "done", "error"]
    content: str | None = None
    source: QASource | None = None
    metrics: RetrievalMetrics | None = None


# ============================================
# Admin/Monitoring Schemas
# ============================================

class HealthResponse(BaseSchema):
    """Health check response."""

    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    uptime_seconds: float
    services: dict[str, Literal["ok", "error", "not_checked"]]
    details: dict[str, Any] = Field(default_factory=dict)


class StatsResponse(BaseSchema):
    """System statistics."""

    total_tenants: int
    total_documents: int
    total_chunks: int
    total_queries_today: int
    average_latency_ms: float
    cache_hit_rate: float
    storage_used_mb: float
    storage_available_mb: float
    active_tasks: int
    queued_tasks: int


class MetricsResponse(BaseSchema):
    """Prometheus metrics (as text)."""

    metrics: str


class ErrorResponse(BaseSchema):
    """Standard error response."""

    error: str
    error_code: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class PaginatedParams(BaseSchema):
    """Common pagination parameters."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class DateRangeFilter(BaseSchema):
    """Date range filter."""

    start: datetime | None = None
    end: datetime | None = None


# ============================================
# Task Status Schemas
# ============================================

class TaskStatusResponse(BaseSchema):
    """Celery task status."""

    task_id: str
    status: Literal["pending", "started", "success", "failure", "retry"]
    progress: float | None = None  # 0.0 to 1.0
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


# Forward reference resolution
DocumentDetailResponse.model_rebuild()