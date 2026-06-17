"""
Prometheus Metrics Setup and Middleware
"""

from prometheus_client import CollectorRegistry, REGISTRY, Counter, Gauge, Histogram, Info

from app.config import settings

# Custom registry for our metrics
METRICS_REGISTRY = CollectorRegistry()

# System info
SYSTEM_INFO = Info(
    "myrag_system",
    "System information",
    registry=METRICS_REGISTRY
)

# Document metrics
DOCUMENTS_TOTAL = Gauge(
    "myrag_documents_total",
    "Total documents indexed",
    ["tenant_id"],
    registry=METRICS_REGISTRY
)

CHUNKS_TOTAL = Gauge(
    "myrag_chunks_total",
    "Total chunks indexed",
    ["tenant_id"],
    registry=METRICS_REGISTRY
)

# Query metrics
QUERIES_TOTAL = Counter(
    "myrag_queries_total",
    "Total queries processed",
    ["tenant_id", "query_type", "mode"],
    registry=METRICS_REGISTRY
)

QUERY_LATENCY = Histogram(
    "myrag_query_latency_ms",
    "Query latency in milliseconds",
    ["tenant_id", "mode"],
    buckets=[50, 100, 200, 300, 500, 1000, 2000, 5000],
    registry=METRICS_REGISTRY
)

# Retrieval metrics
DENSE_RETRIEVAL_LATENCY = Histogram(
    "myrag_dense_retrieval_latency_ms",
    "Dense retrieval latency",
    ["tenant_id"],
    buckets=[10, 25, 50, 100, 200, 500],
    registry=METRICS_REGISTRY
)

SPARSE_RETRIEVAL_LATENCY = Histogram(
    "myrag_sparse_retrieval_latency_ms",
    "Sparse retrieval latency",
    ["tenant_id"],
    buckets=[10, 25, 50, 100, 200, 500],
    registry=METRICS_REGISTRY
)

GRAPH_RETRIEVAL_LATENCY = Histogram(
    "myrag_graph_retrieval_latency_ms",
    "Graph retrieval latency",
    ["tenant_id"],
    buckets=[10, 25, 50, 100, 200, 500],
    registry=METRICS_REGISTRY
)

RERANK_LATENCY = Histogram(
    "myrag_rerank_latency_ms",
    "Reranking latency",
    ["tenant_id", "reranker_type"],
    buckets=[10, 25, 50, 100, 200, 500],
    registry=METRICS_REGISTRY
)

# LLM metrics
LLM_TOKENS_TOTAL = Counter(
    "myrag_llm_tokens_total",
    "Total LLM tokens used",
    ["tenant_id", "model"],
    registry=METRICS_REGISTRY
)

LLM_LATENCY = Histogram(
    "myrag_llm_latency_ms",
    "LLM response latency",
    ["tenant_id", "model"],
    buckets=[100, 500, 1000, 2000, 5000, 10000],
    registry=METRICS_REGISTRY
)

# Cache metrics
CACHE_HIT_TOTAL = Counter(
    "myrag_cache_hit_total",
    "Cache hit count",
    ["tenant_id", "cache_type"],
    registry=METRICS_REGISTRY
)

CACHE_MISS_TOTAL = Counter(
    "myrag_cache_miss_total",
    "Cache miss count",
    ["tenant_id", "cache_type"],
    registry=METRICS_REGISTRY
)

# Task queue metrics
TASKS_TOTAL = Counter(
    "myrag_tasks_total",
    "Total Celery tasks",
    ["task_name", "status"],
    registry=METRICS_REGISTRY
)

TASK_QUEUE_SIZE = Gauge(
    "myrag_task_queue_size",
    "Number of tasks in queue",
    ["queue_name"],
    registry=METRICS_REGISTRY
)

ACTIVE_WORKERS = Gauge(
    "myrag_active_workers",
    "Number of active Celery workers",
    registry=METRICS_REGISTRY
)

# Error metrics
ERRORS_TOTAL = Counter(
    "myrag_errors_total",
    "Total errors",
    ["tenant_id", "error_type"],
    registry=METRICS_REGISTRY
)


def setup_metrics() -> None:
    """Initialize metrics with system info."""
    SYSTEM_INFO.info({
        "version": settings.APP_VERSION,
        "debug": str(settings.DEBUG),
        "embedding_model": settings.EMBEDDING_MODEL,
        "reranker_model": settings.RERANKER_MODEL,
        "llm_provider": settings.LLM_PROVIDER,
    })


def record_query_metrics(
    tenant_id: str,
    query_type: str,
    mode: str,
    latency_ms: float,
) -> None:
    """Record query execution metrics."""
    QUERIES_TOTAL.labels(tenant_id=tenant_id, query_type=query_type, mode=mode).inc()
    QUERY_LATENCY.labels(tenant_id=tenant_id, mode=mode).observe(latency_ms)


def record_retrieval_metrics(
    tenant_id: str,
    dense_latency_ms: float | None = None,
    sparse_latency_ms: float | None = None,
    graph_latency_ms: float | None = None,
) -> None:
    """Record retrieval latency metrics."""
    if dense_latency_ms:
        DENSE_RETRIEVAL_LATENCY.labels(tenant_id=tenant_id).observe(dense_latency_ms)
    if sparse_latency_ms:
        SPARSE_RETRIEVAL_LATENCY.labels(tenant_id=tenant_id).observe(sparse_latency_ms)
    if graph_latency_ms:
        GRAPH_RETRIEVAL_LATENCY.labels(tenant_id=tenant_id).observe(graph_latency_ms)


def record_rerank_metrics(
    tenant_id: str,
    latency_ms: float,
    reranker_type: str = "fine",
) -> None:
    """Record reranking latency."""
    RERANK_LATENCY.labels(tenant_id=tenant_id, reranker_type=reranker_type).observe(latency_ms)


def record_llm_metrics(
    tenant_id: str,
    model: str,
    tokens: int,
    latency_ms: float,
) -> None:
    """Record LLM usage metrics."""
    LLM_TOKENS_TOTAL.labels(tenant_id=tenant_id, model=model).inc(tokens)
    LLM_LATENCY.labels(tenant_id=tenant_id, model=model).observe(latency_ms)


def record_cache_metrics(
    tenant_id: str,
    cache_type: str,
    hit: bool,
) -> None:
    """Record cache hit/miss metrics."""
    if hit:
        CACHE_HIT_TOTAL.labels(tenant_id=tenant_id, cache_type=cache_type).inc()
    else:
        CACHE_MISS_TOTAL.labels(tenant_id=tenant_id, cache_type=cache_type).inc()


def record_error(
    tenant_id: str,
    error_type: str,
) -> None:
    """Record error occurrence."""
    ERRORS_TOTAL.labels(tenant_id=tenant_id, error_type=error_type).inc()


def update_document_count(
    tenant_id: str,
    documents: int,
    chunks: int,
) -> None:
    """Update document and chunk counts."""
    DOCUMENTS_TOTAL.labels(tenant_id=tenant_id).set(documents)
    CHUNKS_TOTAL.labels(tenant_id=tenant_id).set(chunks)